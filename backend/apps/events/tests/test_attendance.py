"""Émargement des sessions et communications présentées (plan L7, K7, K8)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.core.errors import Invalid, NotAllowed, RuleViolation
from apps.core.models import AuditLog
from apps.events.models import Checkin
from apps.events.services import attendance
from apps.events.services import checkin as checkin_services
from apps.events.tests.helpers import confirmed as confirmed_registration
from apps.program.services import planning
from apps.program.services.publication import publish_program
from apps.program.tests.helpers import COMMAND, confirmed, edition, local, session
from apps.submissions.models import StatusHistory
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import user_actor

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    """Programme publié : une session présidée (deux communications), une autre session
    sans président ; un présentateur inscrit et confirmé."""
    current = edition()
    chair = make_member(current, Role.CHAIR)
    room = planning.create_room(current, {"name": "Amphi A"}, actor=COMMAND)
    other_room = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    morning = session(current, local(1, 9), local(1, 10), room=room, title="Santé")
    afternoon = session(current, local(1, 14), local(1, 15), room=other_room, title="Eau")
    first = confirmed(current, duration=20, last="Zadi")
    second = confirmed(current, duration=20, first="Kofi", last="Mensah")
    third = confirmed(current, duration=20, first="Ama", last="Owusu")
    planning.place_submission(morning, first, actor=COMMAND)
    planning.place_submission(morning, second, actor=COMMAND)
    planning.place_submission(afternoon, third, actor=COMMAND)
    session_chair = make_member(current, Role.SESSION_CHAIR)
    Profile.objects.update_or_create(
        user=session_chair, defaults={"first_name": "Koffi", "last_name": "Yao"}
    )
    planning.add_session_role(morning, session_chair, "chair", actor=COMMAND)
    publish_program(current, actor=user_actor(chair))
    for item in (first, second, third):
        item.refresh_from_db()
    return current, morning, afternoon, (first, second, third), session_chair


def slot_of(submission):
    return submission.program_slot.pk


def base(current) -> str:
    return f"/v1/manage/editions/{current.pk}/day/sessions"


# --- Communications présentées (K8) -------------------------------------------------------------


def test_k8_session_chair_marks_presented_in_own_session_only(world):
    current, morning, afternoon, (first, _second, third), session_chair = world
    actor = user_actor(session_chair)
    marked = attendance.mark_presented(current, morning.pk, slot_of(first), actor=actor)
    assert marked.status == S.PRESENTED
    history = StatusHistory.objects.get(submission=first, to_status=S.PRESENTED)
    assert history.actor == session_chair
    # Session qu'il ne préside pas : refus du workflow, même par un appel direct.
    with pytest.raises(NotAllowed):
        attendance.mark_presented(current, afternoon.pk, slot_of(third), actor=actor)
    # Déjà présentée : transition illégale.
    with pytest.raises(RuleViolation):
        attendance.mark_presented(current, morning.pk, slot_of(first), actor=actor)


def test_k8_program_writer_marks_and_corrects_with_a_reason(world):
    current, _morning, afternoon, (_first, _second, third), session_chair = world
    planner = user_actor(make_member(current, Role.OC_MEMBER, oc_function="program"))
    attendance.mark_presented(current, afternoon.pk, slot_of(third), actor=planner)
    with pytest.raises(Invalid):
        attendance.unmark_presented(current, afternoon.pk, slot_of(third), reason="", actor=planner)
    corrected = attendance.unmark_presented(
        current, afternoon.pk, slot_of(third), reason="Erreur de saisie", actor=planner
    )
    assert corrected.status == S.SCHEDULED
    # Le président de séance ne corrige pas (« program.write » seul).
    attendance.mark_presented(current, afternoon.pk, slot_of(third), actor=planner)
    with pytest.raises(NotAllowed):
        attendance.unmark_presented(
            current, afternoon.pk, slot_of(third), reason="x", actor=user_actor(session_chair)
        )


def test_k8_volunteer_cannot_mark_presented(world):
    current, morning, _afternoon, (first, *_rest), _sc = world
    volunteer = user_actor(make_member(current, Role.VOLUNTEER))
    with pytest.raises(NotAllowed):
        attendance.mark_presented(current, morning.pk, slot_of(first), actor=volunteer)


def test_k8_only_the_published_program_counts(world):
    """Une session ajoutée au brouillon après publication ne s'émarge pas ; le président
    désigné au brouillon seulement n'a aucun droit."""
    current, morning, *_rest, session_chair = world
    draft = session(current, local(2, 9), local(2, 10), title="Brouillon")
    planning.add_session_role(draft, session_chair, "chair", actor=COMMAND)
    assert draft.pk not in attendance.published_session_ids(current)
    assert attendance.chaired_session_ids(current, session_chair) == {morning.pk}


# --- Émargement (K7) ---------------------------------------------------------------------------


def test_k7_session_checkin_counts_as_presence_without_reception(world):
    current, morning, afternoon, *_rest = world
    registration = confirmed_registration(current)
    volunteer = user_actor(make_member(current, Role.VOLUNTEER))
    result = checkin_services.check_in(
        current, token=registration.qr_token, session_id=morning.pk, actor=volunteer
    )
    assert result.outcome == "checked_in"
    again = checkin_services.check_in(
        current, token=registration.qr_token, session_id=morning.pk, actor=volunteer
    )
    assert again.outcome == "already_checked_in"
    # Autre lieu, autre pointage : accueil, puis autre session.
    for session_id in (None, afternoon.pk):
        assert (
            checkin_services.check_in(
                current, token=registration.qr_token, session_id=session_id, actor=volunteer
            ).outcome
            == "checked_in"
        )
    assert Checkin.objects.count() == 3
    assert attendance.attendance_counts(current) == {morning.pk: 1, afternoon.pk: 1}


def test_k7_sync_refuses_unpublished_sessions(world):
    current, morning, *_rest = world
    registration = confirmed_registration(current)
    volunteer = user_actor(make_member(current, Role.VOLUNTEER))
    items = [
        {
            "idempotency_key": "sess-0001",
            "token": registration.qr_token,
            "session": morning.pk,
            "scanned_at": None,
        },
        {
            "idempotency_key": "sess-0002",
            "token": registration.qr_token,
            "session": 999999,
            "scanned_at": None,
        },
    ]
    results = checkin_services.synchronize(
        current, items, device="", may_enter_manually=False, actor=volunteer
    )
    assert [r.outcome for r in results] == ["checked_in", "unknown_session"]
    assert Checkin.objects.get().session_id == morning.pk


def test_k7_session_with_attendance_cannot_be_deleted(world):
    current, morning, *_rest = world
    registration = confirmed_registration(current)
    checkin_services.check_in(
        current, token=registration.qr_token, session_id=morning.pk, actor=COMMAND
    )
    with pytest.raises(RuleViolation) as error:
        planning.delete_session(morning, actor=COMMAND)
    assert error.value.code == "in_use"


# --- API ---------------------------------------------------------------------------------------


def test_k7_k8_session_chair_api(world):
    current, morning, afternoon, (first, *_rest), session_chair = world
    registration = confirmed_registration(current)
    client = client_for(session_chair, mfa=False)  # SESSION_CHAIR : sans 2FA (K1)
    # « sessions.chair » : l'édition figure au sélecteur de la gestion.
    listed = [item["id"] for item in client.get("/v1/manage/editions").json()]
    assert listed == [current.pk]
    sessions = client.get(base(current)).json()
    assert [(item["id"], item["chaired"]) for item in sessions] == [(morning.pk, True)]
    slots = sessions[0]["slots"]
    assert [slot["status"] for slot in slots] == ["scheduled", "scheduled"]
    assert slots[0]["presenters"]
    response = client.post(
        f"{base(current)}/{morning.pk}/attendance/scan",
        {"token": registration.qr_token},
        format="json",
    )
    assert response.json()["outcome"] == "checked_in"
    rows = client.get(f"{base(current)}/{morning.pk}/attendance").json()["results"]
    assert [row["registration"]["reference"] for row in rows] == [registration.reference]
    body = client.post(f"{base(current)}/{morning.pk}/slots/{slot_of(first)}/presented").json()
    assert body["slots"][0]["status"] == "presented"
    assert body["attendance"] == 1
    # Ni l'autre session, ni l'export, ni la correction.
    other = f"{base(current)}/{afternoon.pk}"
    assert client.get(f"{other}/attendance").status_code == 403
    assert (
        client.post(
            f"{other}/attendance/scan", {"token": registration.qr_token}, format="json"
        ).status_code
        == 403
    )
    assert client.get(f"{base(current)}/{morning.pk}/attendance/export").status_code == 403
    response = client.post(
        f"{base(current)}/{morning.pk}/slots/{slot_of(first)}/unpresented",
        {"reason": "x"},
        format="json",
    )
    assert response.status_code == 403
    # Rien de l'accueil : ni liste hors ligne, ni pointage d'accueil.
    assert client.get(f"/v1/manage/editions/{current.pk}/checkin/bundle").status_code == 403


def test_k7_volunteer_sees_all_sessions_and_scans_but_does_not_list(world):
    current, morning, afternoon, *_rest = world
    registration = confirmed_registration(current)
    client = client_for(make_member(current, Role.VOLUNTEER))
    sessions = client.get(base(current)).json()
    assert {item["id"] for item in sessions} == {morning.pk, afternoon.pk}
    assert not any(item["chaired"] for item in sessions)
    response = client.post(
        f"{base(current)}/{afternoon.pk}/attendance/scan",
        {"token": registration.qr_token},
        format="json",
    )
    assert response.json()["outcome"] == "checked_in"
    assert client.get(f"{base(current)}/{afternoon.pk}/attendance").status_code == 403
    assert (
        client.post(
            f"{base(current)}/999999/attendance/scan", {"token": "x"}, format="json"
        ).status_code
        == 404
    )


def test_k7_manager_exports_session_attendance(world):
    current, morning, *_rest = world
    registration = confirmed_registration(current)
    checkin_services.check_in(
        current, token=registration.qr_token, session_id=morning.pk, actor=COMMAND
    )
    client = client_for(make_member(current, Role.OC_MEMBER, oc_function="secretariat"))
    response = client.get(f"{base(current)}/{morning.pk}/attendance/export")
    assert response.status_code == 200
    assert registration.reference in response.content.decode("utf-8-sig")
    entry = AuditLog.objects.get(action="checkin.session_exported")
    assert entry.after == {"session": morning.pk, "count": 1}


def test_day_sessions_require_membership(world):
    current, *_rest = world
    assert APIClient().get(base(current)).status_code == 401
    author = make_member(current, Role.AUTHOR)
    assert client_for(author, mfa=False).get(base(current)).status_code == 403
