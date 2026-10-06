"""RG-04 (plan L4, H9, H11) : test de fuite de **chaque** route relecteur. Les auteurs, le
président et l'autre relecteur portent des valeurs traceuses (noms, adresses, institution, nom
du fichier) ; aucune réponse servie au relecteur ne doit en contenir, en double aveugle. La
table ``LEAK_TESTED_ROUTES`` (``test_anonymity.py``) renvoie à ces tests."""

from __future__ import annotations

import pytest

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import TrackFactory
from apps.reviews.anonymity import find_identity_leaks
from apps.reviews.services import assignments
from apps.reviews.services import reviews as services
from apps.reviews.services.grids import create_grid
from apps.reviews.tests.helpers import in_status, reviewer
from apps.submissions import storage
from apps.submissions.models import SubmissionAuthor, SubmissionFile
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import (
    author_user,
    complete_submission,
    open_edition,
    user_actor,
)

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%%EOF\n"
TRACERS = [
    "Kofi",
    "Mensah",
    "kofi.mensah@traceur.example",
    "Adjoua",
    "Traoré",
    "adjoua.traore@traceur.example",
    "Institut Traceur",
    "traceur-original",
    "Pilote",  # président du CS
    "pierre.pilote@traceur.example",
    "Collègue",  # autre relecteur
    "rachel.collegue@traceur.example",
]

FULL = {
    "scores": {
        "originalite": "4",
        "methode": "4",
        "pertinence": "3",
        "redaction": "3",
        "impact": "3",
    },
    "recommendation": "accept",
    "confidence": 4,
    "comment_to_authors": "Travail solide.",
    "comment_to_committee": "RAS.",
}


def _named(user, first: str, last: str, institution: str = "") -> None:
    Profile.objects.update_or_create(
        user=user,
        defaults={
            "first_name": first,
            "last_name": last,
            "institution": institution,
            "country": "CI",
        },
    )


@pytest.fixture
def blind(request):
    """Double aveugle : soumission évaluée par « moi » et « Rachel Collègue », discussion
    ouverte, messages du président et de la collègue ; un troisième relecteur sans évaluation
    (routes d'écriture)."""
    edition = open_edition(double_blind=getattr(request, "param", True))
    edition.reviewers_per_submission = 2
    edition.save()
    track = TrackFactory(edition=edition, code="ia")
    submitter = author_user(first="Kofi", last="Mensah", email="kofi.mensah@traceur.example")
    submission = complete_submission(edition, submitter, track=track)
    SubmissionAuthor.objects.filter(submission=submission).update(institution="Institut Traceur")
    SubmissionAuthor.objects.create(
        submission=submission,
        position=2,
        first_name="Adjoua",
        last_name="Traoré",
        email="adjoua.traore@traceur.example",
        institution="Institut Traceur",
    )
    name, digest = storage.write(PDF)
    SubmissionFile.objects.create(
        submission=submission,
        kind="main",
        version=1,
        storage_name=name,
        original_name="traceur-original.pdf",
        size=len(PDF),
        sha256=digest,
        pages=1,
        is_current=True,
        uploaded_by=submitter,
    )
    in_status(submission, S.SCREENING)
    chair = make_member(edition, Role.SC_CHAIR, email="pierre.pilote@traceur.example")
    _named(chair, "Pierre", "Pilote")
    chair_actor = user_actor(chair)
    create_grid(edition, name="Grille", actor=chair_actor)
    me = reviewer(edition)
    colleague = make_member(edition, Role.SC_MEMBER, email="rachel.collegue@traceur.example")
    _named(colleague, "Rachel", "Collègue")
    mine = assignments.assign(submission, me, actor=chair_actor)
    theirs = assignments.assign(submission, colleague, actor=chair_actor)
    assignments.screen(submission, admissible=True, reason="", actor=chair_actor)
    services.submit_review(theirs, FULL, actor=user_actor(colleague))
    services.submit_review(mine, FULL, actor=user_actor(me))
    services.post_message(submission, "Avis du président.", actor=chair_actor)
    services.post_message(
        submission, "Je maintiens.", actor=user_actor(colleague), assignment=theirs
    )
    third = reviewer(edition)
    pending = assignments.assign(submission, third, actor=chair_actor)
    base = f"/v1/manage/editions/{edition.pk}/reviews"
    return {
        "edition": edition,
        "me": client_for(me),
        "third": client_for(third),
        "mine": f"{base}/assignments/{mine.pk}",
        "pending": f"{base}/assignments/{pending.pk}",
        "base": base,
        "submission": submission,
    }


def assert_clean(response, status: int = 200) -> dict | list:
    assert response.status_code == status, response.content
    payload = response.json()
    assert find_identity_leaks(payload, TRACERS) == []
    return payload


def test_rg04_leak_assignments_list(blind):
    payload = assert_clean(blind["me"].get(f"{blind['base']}/assignments"))
    assert payload[0]["submission"]["reference"] == blind["submission"].reference


def test_rg04_leak_assignment_detail(blind):
    payload = assert_clean(blind["me"].get(blind["mine"]))
    assert payload["submission"]["has_file"] is True
    assert payload["review"]["status"] == "submitted"
    assert payload["double_blind"] is True and payload["discussion_open"] is True


def test_rg04_leak_file_has_a_generic_name(blind):
    response = blind["me"].get(f"{blind['mine']}/file")
    assert response.status_code == 200
    disposition = response["Content-Disposition"]
    assert f'filename="{blind["submission"].reference}.pdf"' in disposition
    assert not [t for t in TRACERS if t.casefold() in disposition.casefold()]


def test_rg04_leak_authors_route_is_closed_in_double_blind(blind):
    assert_clean(blind["me"].get(f"{blind['mine']}/authors"), status=404)


@pytest.mark.parametrize("blind", [False], indirect=True)
def test_open_review_authors_route_gives_names_never_addresses(blind):
    """H9, Q3 : sans double aveugle, noms et affiliations des auteurs ; jamais d'adresse."""
    response = blind["me"].get(f"{blind['mine']}/authors")
    assert response.status_code == 200
    names = [(row["first_name"], row["last_name"]) for row in response.json()]
    assert names == [("Kofi", "Mensah"), ("Adjoua", "Traoré")]
    assert "traceur.example" not in response.content.decode()
    # Les autres routes restent sans identité (le détail n'expose jamais les auteurs).
    detail = blind["me"].get(blind["mine"]).json()
    assert detail["double_blind"] is False
    assert find_identity_leaks(detail, TRACERS) == []


def test_rg04_leak_decline(blind):
    response = blind["third"].post(
        f"{blind['pending']}/decline", {"reason": "Indisponible"}, format="json"
    )
    assert response.status_code == 204 and response.content == b""
    assert_clean(
        blind["me"].post(f"{blind['mine']}/decline", {"reason": "Trop tard"}, format="json"),
        status=409,
    )


def test_rg04_leak_review_save(blind):
    assert_clean(
        blind["third"].put(
            f"{blind['pending']}/review", {"scores": {"originalite": "2.5"}}, format="json"
        )
    )


def test_rg04_leak_review_submit(blind):
    payload = assert_clean(
        blind["third"].post(f"{blind['pending']}/review/submit", FULL, format="json")
    )
    assert payload["version"] == 1


def test_rg04_leak_discussion(blind):
    """H11 : l'autre relecteur et le président n'apparaissent que sous pseudonyme."""
    payload = assert_clean(blind["me"].get(f"{blind['mine']}/discussion"))
    assert len(payload["reviews"]) == 2
    assert sorted(r["mine"] for r in payload["reviews"]) == [False, True]
    ranks = [m["pseudonym_rank"] for m in payload["messages"]]
    assert ranks[0] is None and ranks[1] in {1, 2}
    posted = assert_clean(
        blind["me"].post(f"{blind['mine']}/discussion", {"body": "D'accord."}, format="json"),
        status=201,
    )
    assert posted["messages"][-1]["mine"] is True


def test_rg04_leak_expertise(blind):
    assert_clean(blind["me"].get(f"{blind['base']}/expertise"))
    payload = assert_clean(
        blind["me"].put(f"{blind['base']}/expertise", {"tracks": ["ia"]}, format="json")
    )
    assert payload["tracks"] == ["ia"]


def test_rg04_leak_errors_are_clean_too(blind):
    """Une affectation d'un autre relecteur : 404, sans rien révéler."""
    assert_clean(blind["third"].get(blind["mine"]), status=404)
