"""Confirmation de présentation et retraits (plan L5, I5), côté auteur et côté programme."""

from __future__ import annotations

import pytest

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.core.models import AuditLog
from apps.program.models import PresentationConfirmation, Slot
from apps.program.services import planning
from apps.program.tests.helpers import COMMAND, coauthor, confirmed, edition, local, session
from apps.reviews.tests.helpers import in_status
from apps.submissions.models import SubmissionStatus as S

pytestmark = pytest.mark.django_db


def url(submission, action: str) -> str:
    return f"/v1/submissions/{submission.pk}/{action}"


@pytest.fixture
def received():
    """Communication dont la version finale est reçue, avec un co-auteur."""
    current = edition()
    submission = in_status(confirmed(current), S.CAMERA_READY_RECEIVED)
    coauthor(submission, email="mariam.traore@example.org", presenter=False)
    return submission


def test_i5_confirmation_designates_presenters_and_confirms(received):
    client = client_for(received.submitter, mfa=False)
    before = client.get(f"/v1/submissions/{received.pk}").json()
    assert "confirm_presentation" in before["allowed_actions"]
    response = client.post(url(received, "confirm-presentation"), {"presenters": [2]})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["presentation"]["presenters"] == [2]
    assert AuditLog.objects.filter(action="program.presentation_confirmed").exists()
    # Présentateur désigné : la co-autrice, pas l'auteur qui a soumis (RG-12).
    assert [author.last_name for author in planning.presenters(received)] == ["Traoré"]


@pytest.mark.parametrize("presenters", [[], [3], [1, 1], ["x"]])
def test_i5_presenters_must_be_distinct_authors(received, presenters):
    client = client_for(received.submitter, mfa=False)
    response = client.post(
        url(received, "confirm-presentation"), {"presenters": presenters}, format="json"
    )
    assert response.status_code == 400
    received.refresh_from_db()
    assert received.status == S.CAMERA_READY_RECEIVED


def test_i5_confirmation_only_after_the_final_version(received):
    accepted = in_status(confirmed(received.edition), S.ACCEPTED)
    client = client_for(accepted.submitter, mfa=False)
    response = client.post(url(accepted, "confirm-presentation"), {"presenters": [1]})
    assert (response.status_code, response.json()["code"]) == (409, "invalid_transition")


def test_i5_only_the_submitter_confirms(received):
    other = make_member(received.edition, Role.CHAIR)
    response = client_for(other).post(url(received, "confirm-presentation"), {"presenters": [1]})
    assert response.status_code == 404  # l'auteur ne voit que ses soumissions


def test_i5_workflow_refuses_confirmation_without_presenters(received):
    from apps.core.errors import RuleViolation
    from apps.submissions import workflow
    from apps.submissions.tests.factories import user_actor

    with pytest.raises(RuleViolation):
        workflow.transition(received, S.CONFIRMED, user_actor(received.submitter))


def test_rg12_changing_presenters_of_a_placed_paper_bumps_the_programme(received):
    client = client_for(received.submitter, mfa=False)
    client.post(url(received, "confirm-presentation"), {"presenters": [1]})
    room = planning.create_room(received.edition, {"name": "Amphi"}, actor=COMMAND)
    morning = session(received.edition, local(1, 9), local(1, 10), room=room)
    planning.place_submission(morning, received, actor=COMMAND)
    before = planning.program_state(received.edition).revision
    response = client.post(url(received, "confirm-presentation"), {"presenters": [1, 2]})
    assert response.status_code == 200
    assert PresentationConfirmation.objects.get(submission=received).presenters == [1, 2]
    assert planning.program_state(received.edition).revision == before + 1
    assert AuditLog.objects.filter(action="program.presenters_changed").exists()


@pytest.mark.parametrize("status", [S.CAMERA_READY_RECEIVED, S.CONFIRMED, S.SCHEDULED])
def test_i5_withdrawal_after_acceptance_requires_a_reason(received, status):
    in_status(received, status)
    client = client_for(received.submitter, mfa=False)
    assert client.post(url(received, "withdraw"), {"reason": ""}).status_code == 400
    response = client.post(url(received, "withdraw"), {"reason": "Visa refusé"})
    assert (response.status_code, response.json()["status"]) == (200, "withdrawn")


def test_i5_withdrawal_frees_the_slot_and_alerts_the_programme_team(received):
    current = received.edition
    planner = make_member(current, Role.OC_MEMBER, oc_function="program")
    chair = make_member(current, Role.CHAIR)
    finance = make_member(current, Role.OC_MEMBER, oc_function="finance")
    client = client_for(received.submitter, mfa=False)
    client.post(url(received, "confirm-presentation"), {"presenters": [1]})
    room = planning.create_room(current, {"name": "Amphi"}, actor=COMMAND)
    morning = session(current, local(1, 9), local(1, 10), room=room)
    other = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    planning.place_submission(morning, received, actor=COMMAND, position=0)
    response = client.post(url(received, "withdraw"), {"reason": "Visa refusé"})
    assert response.status_code == 200
    assert not Slot.objects.filter(submission=received).exists()
    other.refresh_from_db()
    assert (other.position, other.starts_at.hour, other.starts_at.minute) == (0, 9, 0)
    emails = OutboxEmail.objects.filter(template_code="program/email/withdrawn")
    assert sorted(emails.values_list("to_email", flat=True)) == sorted([planner.email, chair.email])
    assert finance.email not in emails.values_list("to_email", flat=True)
    assert "Visa refusé" not in emails.first().body_text  # le motif reste dans la gestion
    assert AuditLog.objects.filter(action="program.slot_removed").exists()
