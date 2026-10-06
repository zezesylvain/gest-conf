"""Matrice des droits des routes de gestion (plan L1 §5.9, étude §3.3 ; règles n° 2 et 5).

Un test par case : ``test_matrix[<route>-<méthode>-<profil>-<statut>]``. Les capacités
attendues de chaque profil sont recopiées **à la main** du tableau §5.2 du plan
(``SPEC``), et non lues dans ``apps.accounts.roles`` : la matrice teste le code contre
la spécification, pas contre lui-même. 2FA (``mfa_*``) : cases ajoutées en L1.6.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import InvitationStatus, RoleInvitation, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.invitations import pending_key, token_hash
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import (
    EditionFactory,
    KeyDateFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from apps.core import public_files
from apps.core.models import PublicFileKind
from apps.portal.models import MenuItem, Page, PageSection, Section

pytestmark = pytest.mark.django_db

# --- Spécification (§5.2), recopiée à la main --------------------------------------------

R, W, PUB, ARC = "edition.read", "edition.write", "edition.publish", "edition.archive"
MR, MM, AR = "members.read", "members.manage", "audit.read"
PW = "portal.write"
SR, SE, SX = "submissions.read", "submissions.extend", "submissions.export"
# Plan L4 (H19) : évaluer, piloter l'évaluation, lire toutes les évaluations, décider, publier,
# écrire les grilles.
RW, RM, RA = "reviews.write", "reviews.manage", "reviews.read_all"
DD, DP, GW = "decisions.decide", "decisions.publish", "grids.write"

SPEC: dict[str, set[str]] = {
    # H19 : l'administrateur n'évalue pas et ne décide pas.
    "ADMIN": {R, W, PUB, ARC, MR, MM, AR, PW, SR, SE, SX, RM, RA, GW},
    "CHAIR": {R, W, PUB, MR, MM, AR, PW, SR, SE, SX, RM, RA, DD, DP, GW},
    # D8 validée : lecture du paramétrage ; membres du CS seulement. F10, F8 (plan L3) :
    # soumissions (lecture, dérogations, export). H19 : évalue, pilote, décide, publie.
    "SC_CHAIR": {R, MR, MM, SR, SE, SX, RW, RM, RA, DD, DP, GW},
    "OC_MEMBER": {R, SR},  # D8 : lecture seule (fonction « finances ») ; F10 : soumissions
    "OC_COMMUNICATION": {R, PW, SR},  # E11 (plan L2) : le CO « communication » écrit le portail
    "SC_MEMBER": {RW},  # F10 : pas les soumissions ; H19 : ses affectations seulement
    "AUTHOR": set(),
}
# Profils qui ne sont pas un rôle seul : (rôle, fonction au CO).
PROFILE_ROLES = {"OC_COMMUNICATION": (Role.OC_MEMBER, "communication")}
# Profils sans rôle actif dans l'édition visée : 404 (D5).
NON_MEMBERS = ("no_role", "other_edition_chair", "revoked_chair", "invited")
PROFILES = ("anonymous", *NON_MEMBERS, *SPEC)


@dataclass(frozen=True)
class Case:
    route: str
    method: str
    capability: str
    success: int
    path: str  # gabarit : {e} édition, {track}, {type}, {date}, {role}, {invitation}, {section}…
    body: dict | Callable[[dict], dict] | None = None  # fonction : corps calculé des ids
    recent_auth: bool = False
    format: str = "json"


CASES = [
    Case("manage-edition", "GET", R, 200, "/v1/manage/editions/{e}"),
    Case("manage-edition", "PATCH", W, 200, "/v1/manage/editions/{e}", {"venue": "Palais"}),
    Case(
        "manage-edition-status",
        "POST",
        PUB,
        200,
        "/v1/manage/editions/{e}/status",
        {"status": "published"},
        recent_auth=True,
    ),
    Case("manage-confidentiality", "GET", R, 200, "/v1/manage/editions/{e}/confidentiality"),
    Case(
        "manage-confidentiality",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/confidentiality",
        # Réglage non gelé : la soumission en recevabilité du monde gèle double_blind (RG-19).
        {"max_reviews_per_reviewer": 12},
        recent_auth=True,
    ),
    Case("manage-tracks-list", "GET", R, 200, "/v1/manage/editions/{e}/tracks"),
    Case(
        "manage-tracks-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/tracks",
        {"code": "nouvelle", "name_fr": "Nouvelle"},
    ),
    Case("manage-tracks-detail", "GET", R, 200, "/v1/manage/editions/{e}/tracks/{track}"),
    Case(
        "manage-tracks-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/tracks/{track}",
        {"name_en": "Updated"},
    ),
    Case("manage-tracks-detail", "DELETE", W, 204, "/v1/manage/editions/{e}/tracks/{track}"),
    Case("manage-submission-types-list", "GET", R, 200, "/v1/manage/editions/{e}/submission-types"),
    Case(
        "manage-submission-types-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/submission-types",
        {"code": "poster", "label_fr": "Poster"},
    ),
    Case(
        "manage-submission-types-detail",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/submission-types/{type}",
    ),
    Case(
        "manage-submission-types-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/submission-types/{type}",
        {"label_en": "Talk"},
    ),
    Case(
        "manage-submission-types-detail",
        "DELETE",
        W,
        204,
        "/v1/manage/editions/{e}/submission-types/{type}",
    ),
    Case("manage-key-dates-list", "GET", R, 200, "/v1/manage/editions/{e}/key-dates"),
    Case(
        "manage-key-dates-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/key-dates",
        {"code": "atelier", "at_local": "2027-06-02T09:00", "label_fr": "Atelier"},
    ),
    Case("manage-key-dates-detail", "GET", R, 200, "/v1/manage/editions/{e}/key-dates/{date}"),
    Case(
        "manage-key-dates-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/key-dates/{date}",
        {"is_public": False},
    ),
    Case("manage-key-dates-detail", "DELETE", W, 204, "/v1/manage/editions/{e}/key-dates/{date}"),
    Case("manage-roles", "GET", MR, 200, "/v1/manage/editions/{e}/roles"),
    Case(
        "manage-role-revoke",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/roles/{role}/revoke",
        {"reason": "Fin de mandat"},
        recent_auth=True,
    ),
    Case("manage-invitations", "GET", MR, 200, "/v1/manage/editions/{e}/invitations"),
    Case(
        "manage-invitations",
        "POST",
        MM,
        201,
        "/v1/manage/editions/{e}/invitations",
        {"emails": ["nouveau.relecteur@example.org"], "role": "SC_MEMBER"},
    ),
    Case(
        "manage-invitation-resend",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/invitations/{invitation}/resend",
    ),
    Case(
        "manage-invitation-cancel",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/invitations/{invitation}/cancel",
    ),
    Case("manage-audit", "GET", AR, 200, "/v1/manage/editions/{e}/audit"),
    # --- Portail (lot L2, plan L2 §4) : lecture edition.read, écriture portal.write ----------
    Case("manage-portal-sections-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/sections"),
    Case(
        "manage-portal-sections-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/sections",
        {"code": "bienvenue", "section_type": "rich_text", "body_fr": "<p>Bienvenue</p>"},
    ),
    Case(
        "manage-portal-sections-detail",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/portal/sections/{section}",
    ),
    Case(
        "manage-portal-sections-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/sections/{section}",
        {"title_en": "Welcome"},
    ),
    Case(
        "manage-portal-sections-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/sections/{section}",
    ),
    Case(
        "manage-portal-sections-preview",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/sections/preview",
        {"body_fr": "<p>Aperçu</p>"},
    ),
    Case("manage-portal-pages-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/pages"),
    Case(
        "manage-portal-pages-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/pages",
        {"slug": "acces", "title_fr": "Accès"},
    ),
    Case(
        "manage-portal-pages-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/pages/{page}"
    ),
    Case(
        "manage-portal-pages-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}",
        {"title_en": "Practical information"},
    ),
    Case(
        "manage-portal-pages-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/pages/{page}",
    ),
    Case(
        "manage-portal-pages-attach",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/attach",
        lambda ids: {"section": ids["section"]},
    ),
    Case(
        "manage-portal-pages-detach",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/detach",
        lambda ids: {"section": ids["placed_section"]},
    ),
    Case(
        "manage-portal-pages-reorder",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/reorder",
        lambda ids: {"sections": [ids["placed_section"]]},
    ),
    Case("manage-portal-menu-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/menu"),
    Case(
        "manage-portal-menu-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/menu",
        {"location": "footer", "label_fr": "Contact", "url": "mailto:contact@example.org"},
    ),
    Case("manage-portal-menu-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/menu/{menu}"),
    Case(
        "manage-portal-menu-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/menu/{menu}",
        {"label_en": "Call"},
    ),
    Case(
        "manage-portal-menu-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/menu/{menu}",
    ),
    Case(
        "manage-portal-menu-reorder",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/menu/reorder",
        lambda ids: {"location": "header", "items": list(reversed(ids["header_menu"]))},
    ),
    Case("manage-portal-status", "GET", R, 200, "/v1/manage/editions/{e}/portal/status"),
    # --- Fichiers publics (L2.4) ---------------------------------------------------------------
    Case("manage-portal-files-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/files"),
    Case(
        "manage-portal-files-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/files",
        lambda ids: {
            "file": SimpleUploadedFile("appel.pdf", PDF, "application/pdf"),
            "kind": "document",
        },
        format="multipart",
    ),
    Case(
        "manage-portal-files-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/files/{file}"
    ),
    Case(
        "manage-portal-files-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/files/{file}",
        {"published": True},
    ),
    Case(
        "manage-portal-files-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/files/{file}",
    ),
    Case(
        "manage-portal-files-content",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/portal/files/{file}/content",
    ),
    # --- Soumissions (lot L3, plan L3 §4) ---------------------------------------------------
    Case("manage-submissions-list", "GET", SR, 200, "/v1/manage/editions/{e}/submissions"),
    Case("manage-submissions-stats", "GET", SR, 200, "/v1/manage/editions/{e}/submissions/stats"),
    Case("manage-submissions-export", "GET", SX, 200, "/v1/manage/editions/{e}/submissions/export"),
    Case(
        "manage-submissions-detail",
        "GET",
        SR,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}",
    ),
    Case(
        "manage-submissions-file-content",
        "GET",
        SR,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}/files/{submission_file}/content",
    ),
    Case(
        "manage-submissions-extensions",
        "POST",
        SE,
        201,
        "/v1/manage/editions/{e}/submissions/{submission}/extensions",
        {"until_local": "2099-04-02T23:59", "reason": "Panne de courant"},
    ),
    Case(
        "manage-submissions-extension-revoke",
        "POST",
        SE,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}/extensions/{extension}/revoke",
    ),
    # --- Évaluation (lot L4, plan L4 §4) : grilles -----------------------------------------
    Case("manage-grids-list", "GET", R, 200, "/v1/manage/editions/{e}/grids"),
    Case("manage-grids-list", "POST", GW, 201, "/v1/manage/editions/{e}/grids", {"name": "Poster"}),
    Case("manage-grids-detail", "GET", R, 200, "/v1/manage/editions/{e}/grids/{grid}"),
    Case(
        "manage-grids-detail",
        "PATCH",
        GW,
        200,
        "/v1/manage/editions/{e}/grids/{grid}",
        {"name": "Grille révisée"},
    ),
    Case("manage-grids-detail", "DELETE", GW, 204, "/v1/manage/editions/{e}/grids/{grid}"),
    Case(
        "manage-grids-duplicate", "POST", GW, 201, "/v1/manage/editions/{e}/grids/{grid}/duplicate"
    ),
    # --- Recevabilité, affectations, conflits (L4.2) ------------------------------------------
    Case(
        "manage-review-submissions-list",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions",
    ),
    Case(
        "manage-review-submissions-detail",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}",
    ),
    Case(
        "manage-review-submissions-candidates",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}/candidates",
    ),
    Case(
        "manage-review-submissions-screening",
        "POST",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}/screening",
        {"decision": "reject", "reason": "Hors du champ de la conférence"},
    ),
    Case(
        "manage-assignments-list",
        "POST",
        RM,
        201,
        "/v1/manage/editions/{e}/assignments",
        lambda ids: {"submission": ids["review_submission"], "reviewer": ids["reviewer"]},
    ),
    Case(
        "manage-assignments-detail",
        "PATCH",
        RM,
        200,
        "/v1/manage/editions/{e}/assignments/{assignment}",
        {"due_local": "2099-05-01T23:59"},
    ),
    Case(
        "manage-assignments-cancel",
        "POST",
        RM,
        200,
        "/v1/manage/editions/{e}/assignments/{assignment}/cancel",
        {"reason": "Remplacement"},
    ),
    Case(
        "manage-conflicts-list",
        "POST",
        RM,
        201,
        "/v1/manage/editions/{e}/conflicts",
        lambda ids: {
            "submission": ids["review_submission"],
            "reviewer": ids["reviewer"],
            "reason": "Collaboration récente",
        },
    ),
    Case("manage-portal-poster", "GET", R, 200, "/v1/manage/editions/{e}/portal/poster"),
    Case(
        "manage-portal-poster",
        "PUT",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/poster",
        lambda ids: {"file": ids["image"]},
    ),
]

PDF = b"%PDF-1.7\n%%EOF\n"


def expected_status(case: Case, profile: str) -> int:
    if profile == "anonymous":
        return 401
    if profile in NON_MEMBERS:
        return 404
    return case.success if case.capability in SPEC[profile] else 403


MATRIX = [
    pytest.param(
        case,
        profile,
        expected_status(case, profile),
        id=f"{case.route}-{case.method}-{profile}-{expected_status(case, profile)}",
    )
    for case in CASES
    for profile in PROFILES
]


@pytest.fixture
def world():
    """Édition complète (publiable) avec un membre de chaque rôle et les objets visés."""
    edition = EditionFactory()
    other = EditionFactory()
    track = TrackFactory(edition=edition)
    submission_type = SubmissionTypeFactory(edition=edition)
    KeyDateFactory(edition=edition, code="call_open", at=dt.datetime(2027, 1, 10, tzinfo=dt.UTC))
    key_date = KeyDateFactory(
        edition=edition, code="call_close", at=dt.datetime(2027, 3, 31, tzinfo=dt.UTC)
    )
    users = {}
    for profile in SPEC:
        role, oc_function = PROFILE_ROLES.get(profile, (profile, None))
        users[profile] = make_member(edition, role, oc_function=oc_function)
    users["no_role"] = VerifiedUserFactory()
    users["other_edition_chair"] = make_member(other, Role.CHAIR)
    users["revoked_chair"] = make_member(edition, Role.CHAIR, status=UserRoleStatus.REVOKED)
    invited = VerifiedUserFactory()
    users["invited"] = invited
    now = timezone.now()
    RoleInvitation.objects.create(
        edition=edition,
        email=invited.email,
        role=Role.CHAIR,
        token_hash=token_hash("jeton-invite-chair"),
        pending_key=pending_key(edition.pk, invited.email, Role.CHAIR, ""),
        expires_at=now + dt.timedelta(days=14),
        locale="fr",
        last_sent_at=now,
    )
    # Cibles des actions sur les membres et les invitations : comité scientifique, que
    # tous les détenteurs de members.manage peuvent gérer (SC_CHAIR compris).
    target_member = make_member(edition, Role.SC_MEMBER)
    target_role = UserRole.objects.get(user=target_member, edition=edition)
    invitation = RoleInvitation.objects.create(
        edition=edition,
        email="relecteur.invite@example.org",
        role=Role.SC_MEMBER,
        token_hash=token_hash("jeton-relecteur"),
        pending_key=pending_key(edition.pk, "relecteur.invite@example.org", Role.SC_MEMBER, ""),
        expires_at=now + dt.timedelta(days=14),
        locale="fr",
        last_sent_at=now,
    )
    # Portail : section libre (posable, supprimable), section posée sur une page personnalisée.
    section = Section.objects.create(edition=edition, code="libre", section_type="rich_text")
    placed = Section.objects.create(edition=edition, code="posee", section_type="rich_text")
    page = Page.objects.create(edition=edition, slug="infos", title_fr="Infos")
    PageSection.objects.create(page=page, section=placed, position=0)
    header_menu = list(
        MenuItem.objects.filter(edition=edition, location="header")
        .order_by("position")
        .values_list("pk", flat=True)
    )
    document = public_files.store(
        data=PDF, name="modele.pdf", kind=PublicFileKind.DOCUMENT, edition=edition
    )
    image = public_files.store(
        data=_png(), name="affiche.png", kind=PublicFileKind.IMAGE, edition=edition
    )
    submission, submission_file, extension = _submission_with_extension(edition)
    from apps.core.actor import Actor
    from apps.reviews.services.grids import create_grid

    grid = create_grid(edition, name="Grille", actor=Actor.command("cli:matrice"))
    review_submission, reviewer, assignment = _review_objects(edition)
    ids = {
        "grid": grid.pk,
        "review_submission": review_submission.pk,
        "reviewer": reviewer.pk,
        "assignment": assignment.pk,
        "submission": submission.pk,
        "submission_file": submission_file.pk,
        "extension": extension.pk,
        "file": document.pk,
        "image": image.pk,
        "section": section.pk,
        "placed_section": placed.pk,
        "page": page.pk,
        "menu": header_menu[0],
        "header_menu": header_menu,
        "e": edition.pk,
        "track": track.pk,
        "type": submission_type.pk,
        "date": key_date.pk,
        "role": target_role.pk,
        "invitation": invitation.pk,
    }
    return edition, users, ids


def _submission_with_extension(edition):
    """Brouillon avec un PDF et une dérogation, pour les routes de gestion. Un brouillon, et
    non une soumission : celle-ci gèlerait ``double_blind`` (RG-19) et la case
    « confidentialité » testerait la règle au lieu du droit."""
    from apps.submissions import storage
    from apps.submissions.models import SubmissionExtension, SubmissionFile
    from apps.submissions.tests.factories import author_user, complete_submission

    # Thématique et type propres : ceux de la matrice restent supprimables (sinon 409 in_use).
    submission = complete_submission(edition, author_user())
    name, digest = storage.write(PDF)
    submission_file = SubmissionFile.objects.create(
        submission=submission,
        kind="main",
        version=1,
        storage_name=name,
        original_name="article.pdf",
        size=len(PDF),
        sha256=digest,
        pages=1,
        is_current=True,
        uploaded_by=submission.submitter,
    )
    extension = SubmissionExtension.objects.create(
        submission=submission,
        until=timezone.now() + dt.timedelta(days=2),
        reason="Accordée",
        granted_at=timezone.now(),
    )
    return submission, submission_file, extension


def _review_objects(edition):
    """Soumission en recevabilité (statut posé directement : la clôture de l'appel n'est pas
    passée), un relecteur libre et une affectation active d'un autre relecteur."""
    from apps.reviews.models import ReviewAssignment
    from apps.submissions.models import Submission, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    submission = complete_submission(edition, author_user(first="Kofi", last="Mensah"))
    Submission.objects.filter(pk=submission.pk).update(
        status=SubmissionStatus.SCREENING, reference=f"{edition.code}-0001"
    )
    reviewer = make_member(edition, Role.SC_MEMBER)
    assigned = make_member(edition, Role.SC_MEMBER)
    assignment = ReviewAssignment.objects.create(
        submission=submission,
        reviewer=assigned,
        assigned_at=timezone.now(),
        pseudonym_rank=1,
        active_key=f"{submission.pk}:{assigned.pk}",
    )
    return submission, reviewer, assignment


def _png() -> bytes:
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", (20, 10), "navy").save(output, "PNG")
    return output.getvalue()


def call(client: APIClient, case: Case, ids: dict):
    path = case.path.format(**ids)
    method = getattr(client, case.method.lower())
    if case.body is None:
        return method(path)
    body = case.body(ids) if callable(case.body) else case.body
    return method(path, body, format=case.format)


@pytest.mark.parametrize(("case", "profile", "expected"), MATRIX)
def test_matrix(world, case, profile, expected):
    """Plan L1 §5.9 : anonyme 401, non-membre 404, membre sans capacité 403, sinon succès."""
    _edition, users, ids = world
    client = APIClient() if profile == "anonymous" else client_for(users[profile])
    response = call(client, case, ids)
    assert response.status_code == expected, response.content


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.recent_auth], ids=lambda c: f"{c.route}-{c.method}"
)
def test_matrix_stale_reauthentication(world, case):
    """D12 : sans réauthentification de moins de 5 min → 403 ``reauthentication_required``."""
    _edition, users, ids = world
    response = call(client_for(users["ADMIN"], recent_auth=False), case, ids)
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"


def test_matrix_archived_edition_is_read_only(world):
    """§6.3 : une édition archivée est en lecture seule (409 ``edition_archived``)."""
    edition, users, ids = world
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    client = client_for(users["ADMIN"])
    for case in CASES:
        response = call(client, case, ids)
        if case.method == "GET":
            assert response.status_code == 200, case
        elif case.route != "manage-edition-status":
            assert response.status_code == 409, (case, response.content)
            assert response.json()["code"] == "edition_archived"


def test_manage_response_order_401_404_403_mfa():
    """D5, §4.4 : l'ordre des contrôles ne révèle pas l'existence d'une édition, et la 2FA
    n'est demandée qu'à un membre qui détient la capacité (401 → 404 → 403 → 403 mfa)."""
    edition = EditionFactory()
    author = make_member(edition, Role.AUTHOR)
    stranger = VerifiedUserFactory()
    path = f"/v1/manage/editions/{edition.pk}"
    assert APIClient().get(path).status_code == 401
    assert APIClient().get("/v1/manage/editions/999999").status_code == 401
    assert client_for(stranger).get(path).status_code == 404
    assert client_for(stranger).get("/v1/manage/editions/999999").status_code == 404
    response = client_for(author).get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    # Un non-membre sans 2FA reçoit toujours 404, jamais une demande de 2FA.
    assert client_for(stranger, mfa=False).get(path).status_code == 404
    chair = make_member(edition, Role.CHAIR)
    response = client_for(chair, mfa=False).get(path)
    assert (response.status_code, response.json()["code"]) == (403, "mfa_enrollment_required")


def test_object_of_another_edition_is_404(world):
    _edition, users, ids = world
    other_track = TrackFactory()
    path = f"/v1/manage/editions/{ids['e']}/tracks/{other_track.pk}"
    assert client_for(users["ADMIN"]).get(path).status_code == 404


# --- Liste des éditions (ManageEditionListView, §5.3, D3) -------------------------------


def test_edition_list_cases(world):
    edition, users, _ids = world
    assert APIClient().get("/v1/manage/editions").status_code == 401
    assert client_for(users["no_role"]).get("/v1/manage/editions").json() == []
    assert client_for(users["AUTHOR"]).get("/v1/manage/editions").json() == []
    body = client_for(users["CHAIR"]).get("/v1/manage/editions").json()
    assert [item["id"] for item in body] == [edition.pk]
    # Champs non sensibles seulement.
    assert set(body[0]) == {"id", "code", "title_fr", "title_en", "year", "status"}
    other = client_for(users["other_edition_chair"]).get("/v1/manage/editions").json()
    assert edition.pk not in [item["id"] for item in other]


# --- Filtrage par rôle (§5.4) -----------------------------------------------------------


def test_sc_chair_only_sees_scientific_committee(world):
    _edition, users, ids = world
    client = client_for(users["SC_CHAIR"])
    roles = {
        member["role"] for member in client.get(f"/v1/manage/editions/{ids['e']}/roles").json()
    }
    assert roles == {"SC_CHAIR", "SC_MEMBER"}
    invitations = client.get(f"/v1/manage/editions/{ids['e']}/invitations").json()["results"]
    assert {item["role"] for item in invitations} == {"SC_MEMBER"}


def test_member_email_visible_only_with_members_manage(world):
    _edition, users, ids = world
    members = client_for(users["SC_CHAIR"]).get(f"/v1/manage/editions/{ids['e']}/roles").json()
    assert all("email" in member for member in members)
    # Lecture seule des membres : aucun profil de L1 n'a members.read sans members.manage ;
    # le sérialiseur sans adresse reste le repli (échec fermé), testé directement.
    from apps.accounts.manage_serializers import MemberSerializer

    assert "email" not in MemberSerializer().fields


def test_sc_chair_cannot_invite_chair(world):
    _edition, users, ids = world
    response = client_for(users["SC_CHAIR"]).post(
        f"/v1/manage/editions/{ids['e']}/invitations",
        {"emails": ["x@example.org"], "role": "CHAIR"},
        format="json",
    )
    assert response.status_code == 403


def test_pending_invitation_gives_no_right(world):
    """D6 : un invité ne détient aucun droit, par construction."""
    _edition, users, ids = world
    assert RoleInvitation.objects.filter(status=InvitationStatus.PENDING).exists()
    response = client_for(users["invited"]).get(f"/v1/manage/editions/{ids['e']}")
    assert response.status_code == 404


# --- Complétude (§5.9) ----------------------------------------------------------------------


def _manage_routes():
    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern), pattern

    for route, pattern in walk(get_resolver().url_patterns):
        if route.startswith("v1/manage/editions/<int:edition_id>"):
            actions = getattr(pattern.callback, "actions", {}) or {}
            for method in actions:
                if method not in ("head", "options"):
                    yield pattern.name, method.upper()


def test_every_manage_route_is_in_matrix():
    """Un endpoint ajouté sous v1/manage/editions/{id}/ ne peut pas échapper à la matrice."""
    covered = {(case.route, case.method) for case in CASES}
    missing = sorted(set(_manage_routes()) - covered)
    assert missing == []
