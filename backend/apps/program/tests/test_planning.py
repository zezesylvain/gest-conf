"""Service de planification (plan L5 : I3 à I5, I9, I12, I14 ; RG-12, RG-13)."""

from __future__ import annotations

import pytest
from django.db import connection, transaction

from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.tests.factories import EditionFactory
from apps.core.errors import Invalid, RuleViolation, StaleRevision
from apps.core.models import AuditLog
from apps.program.models import Room, Slot
from apps.program.services import planning
from apps.program.services.planning import ConflictType, detect_conflicts
from apps.program.tests.helpers import (
    COMMAND,
    coauthor,
    confirmed,
    edition,
    local,
    session,
    utc,
)
from apps.reviews.tests.helpers import in_status
from apps.submissions.models import SubmissionStatus as S

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    current = edition()
    room = planning.create_room(current, {"name": "Amphi A", "capacity": 120}, actor=COMMAND)
    return current, room


def kinds(conflicts) -> list[str]:
    return sorted(conflict.kind for conflict in conflicts)


# --- Créneaux calculés (I3) et RG-13 -----------------------------------------------------------


def test_rg13_slots_follow_each_other_with_the_edition_buffer(world):
    current, room = world
    current.session_buffer_minutes = 5
    current.save(update_fields=["session_buffer_minutes"])
    morning = session(current, local(1, 9), local(1, 10, 30), room=room)
    first = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    second = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    third = planning.place_submission(morning, confirmed(current), actor=COMMAND)
    slots = list(morning.slots.order_by("position"))
    assert [slot.pk for slot in slots] == [first.pk, second.pk, third.pk]
    # Durée par défaut du type, sinon 20 minutes (I3) ; tampons de 5 minutes entre créneaux.
    assert [(slot.starts_at, slot.ends_at) for slot in slots] == [
        (utc(1, 9), utc(1, 9, 20)),
        (utc(1, 9, 25), utc(1, 9, 45)),
        (utc(1, 9, 50), utc(1, 10, 10)),
    ]
    assert detect_conflicts(current) == []


def test_rg13_overflow_is_reported_with_its_minutes_not_refused(world):
    current, room = world
    current.session_buffer_minutes = 5
    current.save(update_fields=["session_buffer_minutes"])
    short = session(current, local(1, 9), local(1, 10), room=room)
    for duration in (20, 20, 25):
        planning.place_submission(short, confirmed(current, duration=duration), actor=COMMAND)
    (conflict,) = detect_conflicts(current)
    assert conflict.kind == ConflictType.OVERFLOW
    assert conflict.sessions == (short.pk,)
    assert conflict.minutes == 15  # 20 + 5 + 20 + 5 + 25 = 75 minutes pour 60


def test_insert_at_position_moves_following_slots(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 12), room=room)
    a = planning.place_submission(morning, confirmed(current, duration=30), actor=COMMAND)
    b = planning.place_submission(morning, confirmed(current, duration=30), actor=COMMAND)
    c = planning.place_submission(
        morning, confirmed(current, duration=15), actor=COMMAND, position=0
    )
    assert list(morning.slots.order_by("position").values_list("pk", flat=True)) == [
        c.pk,
        a.pk,
        b.pk,
    ]
    a.refresh_from_db()
    assert a.starts_at == utc(1, 9, 15)


def test_move_between_sessions_compacts_and_reflows_both(world):
    current, room = world
    other_room = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    morning = session(current, local(1, 9), local(1, 11), room=room)
    afternoon = session(current, local(1, 14), local(1, 16), room=other_room)
    first = planning.place_submission(morning, confirmed(current, duration=30), actor=COMMAND)
    second = planning.place_submission(morning, confirmed(current, duration=30), actor=COMMAND)
    planning.move_slot(first, session=afternoon, actor=COMMAND)
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.session_id, first.position, first.starts_at) == (afternoon.pk, 0, utc(1, 14))
    assert (second.position, second.starts_at) == (0, utc(1, 9))


def test_session_moved_later_moves_its_slots(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    slot = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    planning.update_session(
        morning, {"starts_local": local(1, 11), "ends_local": local(1, 12)}, actor=COMMAND
    )
    slot.refresh_from_db()
    assert (slot.starts_at, slot.ends_at) == (utc(1, 11), utc(1, 11, 20))


def test_duration_change_reflows(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    first = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    second = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    planning.update_slot(first, {"duration_min": 30}, actor=COMMAND)
    second.refresh_from_db()
    assert second.starts_at == utc(1, 9, 30)
    with pytest.raises(Invalid):
        planning.update_slot(first, {"duration_min": 0}, actor=COMMAND)
    with pytest.raises(Invalid):  # titre libre : pas pour une communication
        planning.update_slot(first, {"title_fr": "Autre"}, actor=COMMAND)


def test_free_slot_with_invited_speaker(world):
    current, room = world
    plenary = session(current, local(1, 9), local(1, 10), room=room)
    speaker = VerifiedUserFactory()
    slot = planning.add_free_slot(
        plenary, title_fr="Conférence invitée", speaker=speaker, duration_min=45, actor=COMMAND
    )
    assert (slot.submission_id, slot.speaker_id, slot.ends_at) == (None, speaker.pk, utc(1, 9, 45))
    with pytest.raises(Invalid):
        planning.add_free_slot(plenary, title_fr="  ", actor=COMMAND)


# --- I5 : communications programmables ---------------------------------------------------------


def test_i5_only_confirmed_communications_are_programmable(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    accepted = in_status(confirmed(current), S.ACCEPTED)
    with pytest.raises(RuleViolation):
        planning.place_submission(morning, accepted, actor=COMMAND)
    submission = confirmed(current)
    planning.place_submission(morning, submission, actor=COMMAND)
    with pytest.raises(Invalid):  # une communication n'occupe qu'un créneau
        planning.place_submission(morning, submission, actor=COMMAND)
    assert list(planning.to_schedule(current)) == []


def test_communication_of_another_edition_is_refused(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    with pytest.raises(Invalid):
        planning.place_submission(morning, confirmed(edition()), actor=COMMAND)


def test_deleting_a_session_returns_its_communications_to_schedule(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    submission = confirmed(current)
    planning.place_submission(morning, submission, actor=COMMAND)
    planning.delete_session(morning, actor=COMMAND)
    assert list(planning.to_schedule(current)) == [submission]
    assert AuditLog.objects.filter(action="program.session_deleted").exists()


# --- RG-12 : salles et personnes ---------------------------------------------------------------


def test_rg12_two_sessions_in_the_same_room_at_the_same_time(world):
    current, room = world
    first = session(current, local(1, 9), local(1, 10, 30), room=room)
    second = session(current, local(1, 10), local(1, 11), room=room)
    session(current, local(1, 11), local(1, 12), room=room)  # contiguë : pas de conflit
    (conflict,) = detect_conflicts(current)
    assert (conflict.kind, conflict.sessions) == (ConflictType.ROOM, (first.pk, second.pk))


def test_rg12_session_chair_in_two_places(world):
    current, room = world
    other_room = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    first = session(current, local(1, 9), local(1, 10), room=room)
    second = session(current, local(1, 9, 30), local(1, 11), room=other_room)
    chair = VerifiedUserFactory()
    planning.add_session_role(first, chair, "chair", actor=COMMAND)
    planning.add_session_role(second, chair, "discussant", actor=COMMAND)
    (conflict,) = detect_conflicts(current)
    assert (conflict.kind, conflict.sessions) == (ConflictType.PERSON, (first.pk, second.pk))


def test_rg12_presenter_without_account_identified_by_address(world):
    current, room = world
    other_room = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    first = session(current, local(1, 9), local(1, 10), room=room)
    second = session(current, local(1, 9), local(1, 10), room=other_room)
    one, two = confirmed(current, duration=30), confirmed(current, duration=30)
    coauthor(one, email="mariam.traore@example.org")
    coauthor(two, email="Mariam.Traore@example.org")  # même personne, casse différente
    planning.place_submission(first, one, actor=COMMAND)
    planning.place_submission(second, two, actor=COMMAND)
    conflicts = [item for item in detect_conflicts(current) if item.person == "Mariam Traoré"]
    assert len(conflicts) == 1
    assert "@" not in conflicts[0].person  # jamais d'adresse dans un conflit


def test_rg12_same_person_twice_in_the_same_session_is_not_a_conflict(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 11), room=room)
    submission = confirmed(current, duration=30)
    planning.place_submission(morning, submission, actor=COMMAND)
    planning.add_session_role(morning, submission.submitter, "chair", actor=COMMAND)
    assert detect_conflicts(current) == []


def test_rg12_presenters_come_from_the_confirmation(world):
    """I5 : seul le présentateur désigné compte, pas les autres auteurs."""
    from apps.program.models import PresentationConfirmation

    current, room = world
    other_room = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    first = session(current, local(1, 9), local(1, 10), room=room)
    second = session(current, local(1, 9), local(1, 10), room=other_room)
    one, two = confirmed(current, duration=30), confirmed(current, duration=30)
    coauthor(one, email="commun@example.org")
    coauthor(two, email="commun@example.org")
    PresentationConfirmation.objects.create(
        submission=two, presenters=[1], confirmed_at=two.updated_at, confirmed_by=two.submitter
    )
    planning.place_submission(first, one, actor=COMMAND)
    planning.place_submission(second, two, actor=COMMAND)
    assert detect_conflicts(current) == []


# --- Heures (I12), salles (I9), révision (I14), journal ----------------------------------------


def test_i12_nonexistent_local_time_is_refused_on_the_session_field():
    paris = EditionFactory(timezone="Europe/Paris", start_date=None, end_date=None)
    with pytest.raises(Invalid) as error:
        planning.create_session(
            paris,
            {
                "kind": "parallel",
                "title_fr": "Nuit",
                "starts_local": local(1, 9).replace(month=3, day=28, hour=2, minute=30),
                "ends_local": local(1, 9).replace(month=3, day=28, hour=4),
            },
            actor=COMMAND,
        )
    assert "starts_local" in error.value.fields


def test_i12_session_must_take_place_during_the_edition(world):
    current, room = world
    with pytest.raises(Invalid) as error:
        session(current, local(5, 9), local(5, 10), room=room)
    assert "starts_local" in error.value.fields
    with pytest.raises(Invalid) as error:
        session(current, local(1, 10), local(1, 9), room=room)
    assert "ends_local" in error.value.fields


def test_i9_room_in_use_is_not_deleted_but_deactivated(world):
    current, room = world
    session(current, local(1, 9), local(1, 10), room=room)
    with pytest.raises(RuleViolation) as error:
        planning.delete_room(room, actor=COMMAND)
    assert error.value.code == "in_use"
    planning.update_room(room, {"is_active": False}, actor=COMMAND)
    with pytest.raises(Invalid):  # salle désactivée : plus de nouvelle session
        session(current, local(2, 9), local(2, 10), room=room)
    with pytest.raises(Invalid):
        planning.create_room(current, {"name": "amphi a"}, actor=COMMAND)
    with pytest.raises(Invalid):
        planning.create_room(current, {"name": "Salle C", "equipment": ["laser"]}, actor=COMMAND)


def test_i14_stale_revision_is_refused_and_each_write_bumps_it(world):
    current, room = world
    state = planning.program_state(current)
    before = state.revision
    morning = session(current, local(1, 9), local(1, 10), room=room)
    state.refresh_from_db()
    assert state.revision == before + 1
    with pytest.raises(StaleRevision):
        planning.update_session(morning, {"title_fr": "Matin"}, actor=COMMAND, revision=before)
    planning.update_session(morning, {"title_fr": "Matin"}, actor=COMMAND, revision=before + 1)


def test_rg17_every_write_is_audited(world):
    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    slot = planning.place_submission(morning, confirmed(current), actor=COMMAND)
    planning.update_slot(slot, {"duration_min": 25}, actor=COMMAND)
    planning.remove_slot(slot, actor=COMMAND)
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {
        "program.room_created",
        "program.session_created",
        "program.slot_placed",
        "program.slot_updated",
        "program.slot_removed",
    } <= actions
    assert not Slot.objects.exists()


@pytest.mark.mariadb_only  # SQLite verrouille la base entière : sans objet
@pytest.mark.django_db(transaction=True)
def test_concurrent_placements_are_serialized_without_lost_update():
    """I14 : deux placements simultanés, mis en série par le verrou de l'état du programme ;
    créneaux contigus, révision incrémentée deux fois."""
    import threading

    current = edition()
    room = Room.objects.create(edition=current, name="Amphi")
    morning = session(current, local(1, 9), local(1, 12), room=room)
    submissions = [confirmed(current, duration=30) for _ in range(4)]
    start = planning.program_state(current).revision
    errors: list[str] = []

    def place(submission) -> None:
        try:
            with transaction.atomic():
                planning.place_submission(morning, submission, actor=COMMAND)
        except Exception as error:  # pragma: no cover - diagnostic du test
            errors.append(repr(error))
        finally:
            connection.close()

    threads = [threading.Thread(target=place, args=(item,)) for item in submissions]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert errors == []
    slots = list(morning.slots.order_by("position"))
    assert [slot.position for slot in slots] == [0, 1, 2, 3]
    assert [slot.starts_at for slot in slots] == [
        utc(1, 9),
        utc(1, 9, 30),
        utc(1, 10),
        utc(1, 10, 30),
    ]
    assert planning.program_state(current).revision == start + 4


def test_integrity_check_detects_inconsistent_slots(world):
    from apps.program.integrity import check_slots

    current, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    slot = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    assert check_slots() == []
    Slot.objects.filter(pk=slot.pk).update(starts_at=utc(1, 9, 5))
    in_status(slot.submission, S.ACCEPTED)
    problems = check_slots()
    assert f"créneau {slot.pk} : position ou horaire incohérents" in problems
    assert f"créneau {slot.pk} : communication ni confirmée ni programmée" in problems
