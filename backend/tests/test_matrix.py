"""Matrice des droits des routes de gestion (plan L1 §5.9, étude §3.3 ; règles n° 2 et 5).

Un test par case : ``test_matrix[<route>-<méthode>-<profil>-<statut>]``. Les capacités
attendues de chaque profil sont recopiées **à la main** du tableau §5.2 du plan
(``SPEC``), et non lues dans ``apps.accounts.roles`` : la matrice teste le code contre
la spécification, pas contre lui-même. 2FA (``mfa_*``) : cases ajoutées en L1.6.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest
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

pytestmark = pytest.mark.django_db

# --- Spécification (§5.2), recopiée à la main --------------------------------------------

R, W, PUB, ARC = "edition.read", "edition.write", "edition.publish", "edition.archive"
MR, MM, AR = "members.read", "members.manage", "audit.read"

SPEC: dict[str, set[str]] = {
    "ADMIN": {R, W, PUB, ARC, MR, MM, AR},
    "CHAIR": {R, W, PUB, MR, MM, AR},
    "SC_CHAIR": {R, MR, MM},  # D8 validée : lecture du paramétrage ; membres du CS seulement
    "OC_MEMBER": {R},  # D8 : lecture seule
    "SC_MEMBER": set(),
    "AUTHOR": set(),
}
# Profils sans rôle actif dans l'édition visée : 404 (D5).
NON_MEMBERS = ("no_role", "other_edition_chair", "revoked_chair", "invited")
PROFILES = ("anonymous", *NON_MEMBERS, *SPEC)


@dataclass(frozen=True)
class Case:
    route: str
    method: str
    capability: str
    success: int
    path: str  # gabarit : {e} édition, {track}, {type}, {date}, {role}, {invitation}
    body: dict | None = None
    recent_auth: bool = False


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
        {"double_blind": False},
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
]


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
    users = {role: make_member(edition, role) for role in SPEC}
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
    ids = {
        "e": edition.pk,
        "track": track.pk,
        "type": submission_type.pk,
        "date": key_date.pk,
        "role": target_role.pk,
        "invitation": invitation.pk,
    }
    return edition, users, ids


def call(client: APIClient, case: Case, ids: dict):
    path = case.path.format(**ids)
    method = getattr(client, case.method.lower())
    if case.body is None:
        return method(path)
    return method(path, case.body, format="json")


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
