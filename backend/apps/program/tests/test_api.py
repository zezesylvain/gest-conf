"""API de gestion du programme (plan L5 §4 ; I1, I9, I10, I14, I15 ; RG-12, RG-13)."""

from __future__ import annotations

import pytest

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.program.models import Room, Session, SessionRole, Slot
from apps.program.services import planning
from apps.program.tests.helpers import COMMAND, confirmed, edition, local, session

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    current = edition()
    planner = make_member(current, Role.OC_MEMBER, oc_function="program")
    room = planning.create_room(current, {"name": "Amphi A"}, actor=COMMAND)
    return current, client_for(planner), room


def base(current) -> str:
    return f"/v1/manage/editions/{current.pk}/program"


def revision(client, current) -> int:
    return client.get(base(current)).json()["revision"]


def test_board_lists_rooms_sessions_to_schedule_and_days(world):
    current, client, room = world
    waiting = confirmed(current, duration=25)
    session(current, local(1, 9), local(1, 10), room=room, title="Matin")
    board = client.get(base(current)).json()
    assert board["days"] == ["2027-06-01", "2027-06-02", "2027-06-03"]
    assert [item["name"] for item in board["rooms"]] == ["Amphi A"]
    (item,) = board["sessions"]
    assert (item["title_fr"], item["starts_local"], item["room"]) == (
        "Matin",
        "2027-06-01T09:00:00",
        room.pk,
    )
    (pending,) = board["to_schedule"]
    assert (pending["id"], pending["default_duration_min"], pending["presenters"]) == (
        waiting.pk,
        25,
        ["Awa Zadi"],
    )
    assert board["unpublished_changes"] is True
    assert board["conflicts"] == []


def test_session_created_at_local_time_then_placement_with_if_match(world):
    current, client, room = world
    submission = confirmed(current, duration=20)
    response = client.post(
        f"{base(current)}/sessions",
        {
            "kind": "parallel",
            "title_fr": "Santé",
            "room": room.pk,
            "starts_local": "2027-06-01T14:00",
            "ends_local": "2027-06-01T15:00",
        },
        HTTP_IF_MATCH=str(revision(client, current)),
    )
    assert response.status_code == 201
    created = Session.objects.get(title_fr="Santé")
    board = response.json()
    response = client.post(
        f"{base(current)}/sessions/{created.pk}/slots",
        {"submission": submission.pk},
        HTTP_IF_MATCH=str(board["revision"]),
    )
    assert response.status_code == 201
    (item,) = response.json()["sessions"]
    assert item["slots"][0]["submission"]["reference"] == submission.reference
    assert item["slots"][0]["ends_at"].startswith("2027-06-01T14:20")
    assert response.json()["to_schedule"] == []


def test_i14_stale_revision_is_412(world):
    current, client, room = world
    stale = revision(client, current)
    session(current, local(1, 9), local(1, 10), room=room)  # écriture d'un autre membre
    response = client.post(f"{base(current)}/rooms", {"name": "Salle B"}, HTTP_IF_MATCH=str(stale))
    assert response.status_code == 412
    assert response.json()["code"] == "stale_revision"
    assert not Room.objects.filter(name="Salle B").exists()


def test_slot_moved_and_resized_in_one_request(world):
    current, client, room = world
    morning = session(current, local(1, 9), local(1, 11), room=room)
    first = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    second = planning.place_submission(morning, confirmed(current, duration=20), actor=COMMAND)
    response = client.patch(
        f"{base(current)}/slots/{second.pk}",
        {"duration_min": 30, "position": 0},
        HTTP_IF_MATCH=str(revision(client, current)),
    )
    assert response.status_code == 200
    slots = response.json()["sessions"][0]["slots"]
    assert [(slot["id"], slot["duration_min"]) for slot in slots] == [
        (second.pk, 30),
        (first.pk, 20),
    ]


def test_rg12_conflicts_returned_with_names_never_addresses(world):
    current, client, room = world
    other = planning.create_room(current, {"name": "Salle B"}, actor=COMMAND)
    first = session(current, local(1, 9), local(1, 10), room=room)
    second = session(current, local(1, 9), local(1, 10), room=other)
    chair = make_member(current, Role.SC_MEMBER)
    Profile.objects.update_or_create(
        user=chair, defaults={"first_name": "Koffi", "last_name": "Yao"}
    )
    for item in (first, second):
        response = client.post(
            f"{base(current)}/sessions/{item.pk}/roles", {"user": chair.pk, "role": "chair"}
        )
        assert response.status_code == 201
    (conflict,) = response.json()["conflicts"]
    assert (conflict["kind"], conflict["person"]) == ("person", "Koffi Yao")
    assert chair.email not in str(response.json())


def test_i10_session_roles_only_for_people_of_the_edition(world):
    current, client, room = world
    morning = session(current, local(1, 9), local(1, 10), room=room)
    stranger = make_member(edition(), Role.CHAIR)
    response = client.post(
        f"{base(current)}/sessions/{morning.pk}/roles", {"user": stranger.pk, "role": "chair"}
    )
    assert response.status_code == 400
    member = make_member(current, Role.SESSION_CHAIR)
    client.post(
        f"{base(current)}/sessions/{morning.pk}/roles", {"user": member.pk, "role": "chair"}
    )
    item = SessionRole.objects.get(session=morning)
    assert client.delete(f"{base(current)}/session-roles/{item.pk}").status_code == 200
    assert not SessionRole.objects.exists()


def test_people_search_gives_names_and_roles_never_addresses(world):
    current, client, _room = world
    member = make_member(current, Role.SPEAKER)
    Profile.objects.update_or_create(
        user=member, defaults={"first_name": "Aïcha", "last_name": "Bamba", "institution": "INP"}
    )
    response = client.get(f"{base(current)}/people", {"q": "bamb"})
    assert response.status_code == 200
    assert response.json() == [
        {"id": member.pk, "name": "Aïcha Bamba", "institution": "INP", "roles": ["SPEAKER"]}
    ]
    assert member.email not in response.content.decode()


def test_free_slot_with_invited_speaker_through_the_api(world):
    current, client, room = world
    plenary = session(current, local(1, 9), local(1, 10), room=room)
    speaker = make_member(current, Role.SPEAKER)
    response = client.post(
        f"{base(current)}/sessions/{plenary.pk}/slots",
        {"title_fr": "Conférence invitée", "speaker": speaker.pk, "duration_min": 45},
    )
    assert response.status_code == 201
    slot = Slot.objects.get(session=plenary)
    assert (slot.speaker_id, slot.duration_min) == (speaker.pk, 45)
    both = client.post(
        f"{base(current)}/sessions/{plenary.pk}/slots",
        {"title_fr": "X", "submission": confirmed(current).pk},
    )
    assert both.status_code == 400


def test_objects_of_another_edition_are_404(world):
    current, client, _room = world
    other = edition()
    foreign_room = planning.create_room(other, {"name": "Ailleurs"}, actor=COMMAND)
    foreign = session(other, local(1, 9), local(1, 10), room=foreign_room)
    assert (
        client.patch(f"{base(current)}/sessions/{foreign.pk}", {"title_fr": "X"}).status_code == 404
    )
    assert (
        client.patch(f"{base(current)}/rooms/{foreign_room.pk}", {"name": "X"}).status_code == 404
    )
    assert (
        client.post(f"{base(current)}/sessions/{foreign.pk}/slots", {"title_fr": "X"}).status_code
        == 404
    )


def test_room_in_use_cannot_be_deleted_through_the_api(world):
    current, client, room = world
    session(current, local(1, 9), local(1, 10), room=room)
    response = client.delete(f"{base(current)}/rooms/{room.pk}")
    assert (response.status_code, response.json()["code"]) == (409, "in_use")


def test_chair_reads_but_does_not_write_the_programme(world):
    """I1 : le Chair lit (et publiera) le programme, sans l'écrire."""
    current, _client, _room = world
    chair = client_for(make_member(current, Role.CHAIR))
    assert chair.get(base(current)).status_code == 200
    assert chair.post(f"{base(current)}/rooms", {"name": "Salle C"}).status_code == 403
