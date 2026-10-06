"""Publication du programme, programme public, « Mon passage » et iCal (plan L5 : I6 à I8,
I11, I16 ; RG-12, RG-13, RG-17)."""

from __future__ import annotations

import pytest
from allauth.account.models import EmailAddress
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.services.account import record_consent
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.core.errors import RuleViolation
from apps.core.models import AuditLog
from apps.program.models import ProgramPublication
from apps.program.services import planning
from apps.program.services.publication import publish_program
from apps.program.tests.helpers import COMMAND, coauthor, confirmed, edition, local, session
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import user_actor

pytestmark = pytest.mark.django_db

TRACER = "traceur.adresse@example.org"


@pytest.fixture
def world():
    """Édition courante, une session avec deux communications (dont une co-autrice sans
    compte), un président de séance, le Chair qui publie."""
    from apps.conferences.services import set_current_edition

    current = edition()
    set_current_edition(current.conference, current, actor=COMMAND)
    chair = make_member(current, Role.CHAIR)
    room = planning.create_room(
        current, {"name": "Amphi A", "access_note": "Bâtiment B"}, actor=COMMAND
    )
    morning = session(current, local(1, 9), local(1, 10), room=room, title="Santé")
    planning.update_session(morning, {"instructions": "Clé USB à 8 h 45"}, actor=COMMAND)
    first = confirmed(current, duration=20, last="Zadi")
    coauthor(first, email=TRACER, first="Mariam", last="Traoré", presenter=False)
    second = confirmed(current, duration=20, first="Kofi", last="Mensah")
    planning.place_submission(morning, first, actor=COMMAND)
    planning.place_submission(morning, second, actor=COMMAND)
    session_chair = make_member(current, Role.SESSION_CHAIR)
    Profile.objects.update_or_create(
        user=session_chair, defaults={"first_name": "Koffi", "last_name": "Yao"}
    )
    planning.add_session_role(morning, session_chair, "chair", actor=COMMAND)
    return current, chair, morning, first, second, session_chair


def publish(current, chair):
    return publish_program(current, actor=user_actor(chair))


# --- Publication (I6) ----------------------------------------------------------------------


def test_i6_publication_freezes_a_snapshot_and_schedules_placed_papers(world):
    current, chair, _morning, first, second, _sc = world
    publication = publish(current, chair)
    assert publication.version == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.status, second.status) == (S.SCHEDULED, S.SCHEDULED)
    state = planning.program_state(current)
    assert (state.published_version, state.published_revision) == (1, state.revision)
    log = AuditLog.objects.get(action="program.published")
    assert log.after["version"] == 1
    with pytest.raises(RuleViolation) as error:  # rien n'a changé
        publish(current, chair)
    assert error.value.code == "program_unchanged"


def test_i6_rg12_rg13_publication_refused_while_conflicts_remain(world):
    current, chair, morning, *_rest = world
    planning.update_slot(morning.slots.first(), {"duration_min": 50}, actor=COMMAND)
    with pytest.raises(RuleViolation) as error:
        publish(current, chair)
    assert error.value.code == "program_conflicts"
    assert not ProgramPublication.objects.exists()


def test_i6_only_the_chair_publishes(world):
    current, _chair, *_rest = world
    planner = make_member(current, Role.OC_MEMBER, oc_function="program")
    with pytest.raises(Exception):  # noqa: B017 - refus du workflow ou de la vue
        publish_program(current, actor=user_actor(planner))
    response = client_for(planner).post(f"/v1/manage/editions/{current.pk}/program/publish")
    assert response.status_code == 403


def test_i6_paper_removed_from_published_programme_returns_to_confirmed(world):
    current, chair, _morning, first, *_rest = world
    publish(current, chair)
    planning.remove_slot(first.program_slot, actor=COMMAND)
    publish(current, chair)
    first.refresh_from_db()
    assert first.status == S.CONFIRMED


# --- Notifications ciblées (I16) -------------------------------------------------------------


def test_i16_everyone_concerned_is_told_once_then_only_who_changed(world):
    current, chair, _morning, first, second, session_chair = world
    publish(current, chair)
    passage = OutboxEmail.objects.filter(template_code="program/email/passage")
    recipients = set(passage.values_list("to_email", flat=True))
    # Auteurs présentateurs (compte), co-autrice sans compte (adresse), président de séance.
    assert recipients == {first.submitter.email, second.submitter.email, session_chair.email}
    assert TRACER not in recipients  # co-autrice non présentatrice : pas de passage
    body = passage.get(to_email=first.submitter.email).body_text
    assert "Amphi A" in body and "09:00" in body
    # Second ordre : seul le second passage change (on intervertit les créneaux).
    planning.move_slot(second.program_slot, position=0, actor=COMMAND)
    publish(current, chair)
    second_round = passage.count()
    changed = set(
        OutboxEmail.objects.filter(
            template_code="program/email/passage", idempotency_key__contains=":2:"
        ).values_list("to_email", flat=True)
    )
    assert changed == {first.submitter.email, second.submitter.email}
    assert second_round == 5


def test_i16_presenter_without_account_is_written_to_at_the_author_address(world):
    current, chair, _morning, first, *_rest = world
    from apps.program.models import PresentationConfirmation

    PresentationConfirmation.objects.create(
        submission=first,
        presenters=[2],
        confirmed_at=first.updated_at,
        confirmed_by=first.submitter,
    )
    publish(current, chair)
    email = OutboxEmail.objects.get(template_code="program/email/passage", to_email=TRACER)
    assert email.to_user_id is None
    assert "créez un compte" in email.body_text


# --- Programme public (I7) -------------------------------------------------------------------


def test_i7_public_programme_404_until_published_then_whitelisted(world):
    current, chair, morning, first, *_rest = world
    anonymous = APIClient()
    assert anonymous.get("/v1/public/program").status_code == 404
    publish(current, chair)
    summary = anonymous.get("/v1/public/program").json()
    (day,) = summary["days"]
    assert day["date"] == "2027-06-01"
    assert day["sessions"][0]["slot_count"] == 2
    detail = anonymous.get("/v1/public/program/days/2027-06-01").json()
    (item,) = detail["sessions"]
    assert item["room"]["name"] == "Amphi A"
    assert item["chairs"] == [{"role": "chair", "name": "Koffi Yao", "institution": ""}]
    assert [author["name"] for author in item["slots"][0]["authors"]] == [
        "Awa Zadi",
        "Mariam Traoré",
    ]
    session = anonymous.get(f"/v1/public/program/sessions/{morning.pk}")
    assert session.status_code == 200
    for response in (summary, detail, session.json()):
        text = str(response)
        # Ni adresse, ni clé de personne, ni consignes internes, ni identifiant de compte.
        for leak in (TRACER, first.submitter.email, "user:", "email:", "Clé USB"):
            assert leak not in text
    assert anonymous.get("/v1/public/program/days/2027-06-02").status_code == 404


def test_i7_draft_changes_invisible_until_republished(world):
    current, chair, morning, *_rest = world
    publish(current, chair)
    planning.update_session(morning, {"title_fr": "Nouveau titre"}, actor=COMMAND)
    detail = APIClient().get(f"/v1/public/program/sessions/{morning.pk}").json()
    assert detail["title_fr"] == "Santé"


def test_i11_speaker_bio_and_photo_only_with_consent(world):
    current, chair, _morning, *_rest = world
    from apps.accounts.models import ConsentKind, ConsentSource

    speaker = make_member(current, Role.SPEAKER)
    Profile.objects.update_or_create(
        user=speaker, defaults={"first_name": "Ama", "last_name": "Owusu", "bio": "Biologiste."}
    )
    plenary = session(current, local(1, 11), local(1, 12), title="Plénière")
    planning.add_free_slot(plenary, title_fr="Conférence invitée", speaker=speaker, actor=COMMAND)
    publish(current, chair)
    detail = APIClient().get(f"/v1/public/program/sessions/{plenary.pk}").json()
    assert detail["slots"][0]["speaker"]["bio"] == ""
    record_consent(
        speaker,
        ConsentKind.DIRECTORY_LISTING,
        True,
        source=ConsentSource.ACCOUNT,
        actor=user_actor(speaker),
    )
    planning.mark_changed(current)
    publish(current, chair)
    detail = APIClient().get(f"/v1/public/program/sessions/{plenary.pk}").json()
    assert detail["slots"][0]["speaker"]["bio"] == "Biologiste."


# --- « Mon passage » et iCal (I8) ------------------------------------------------------------


def test_i8_my_agenda_from_the_published_programme_only(world):
    current, chair, _morning, first, _second, session_chair = world
    client = client_for(session_chair, mfa=False)
    assert client.get("/v1/me/agenda").json() == []
    publish(current, chair)
    (entry,) = client.get("/v1/me/agenda").json()
    assert (entry["role"], entry["session"]["title_fr"], entry["room"]["name"]) == (
        "chair",
        "Santé",
        "Amphi A",
    )
    assert entry["instructions"] == "Clé USB à 8 h 45"
    assert entry["co_speakers"] == ["Awa Zadi", "Kofi Mensah"]
    (mine,) = client_for(first.submitter, mfa=False).get("/v1/me/agenda").json()
    assert (mine["role"], mine["reference"], mine["chairs"]) == (
        "presenter",
        first.reference,
        ["Koffi Yao"],
    )


def test_i8_coauthor_who_creates_an_account_later_finds_the_passage(world):
    current, chair, _morning, first, *_rest = world
    from apps.program.models import PresentationConfirmation

    PresentationConfirmation.objects.create(
        submission=first,
        presenters=[2],
        confirmed_at=first.updated_at,
        confirmed_by=first.submitter,
    )
    publish(current, chair)
    later = VerifiedUserFactory(email=TRACER)
    EmailAddress.objects.filter(user=later).update(email=TRACER)
    (entry,) = client_for(later, mfa=False).get("/v1/me/agenda").json()
    assert entry["role"] == "presenter"


def test_i8_ical_download(world):
    current, chair, _morning, _first, _second, session_chair = world
    publish(current, chair)
    client = client_for(session_chair, mfa=False)
    response = client.get("/v1/me/agenda.ics")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/calendar; charset=utf-8"
    assert response["Cache-Control"] == "private, no-store"
    body = response.content.decode()
    assert body.startswith("BEGIN:VCALENDAR\r\n")
    assert "DTSTART:20270601T090000Z\r\n" in body
    assert "LOCATION:Amphi A\r\n" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert APIClient().get("/v1/me/agenda.ics").status_code in (401, 403)


def test_ical_escaping_and_folding_rfc5545():
    import datetime as dt

    from apps.program import ical

    event = ical.Event(
        uid="1@x",
        starts_at=dt.datetime(2027, 6, 1, 9, tzinfo=dt.UTC),
        ends_at=dt.datetime(2027, 6, 1, 10, tzinfo=dt.UTC),
        summary="Séance ; IA, santé \\ imagerie",
        description="Ligne 1\nLigne 2 " + "é" * 60,
    )
    body = ical.calendar([event], stamp=dt.datetime(2026, 10, 6, tzinfo=dt.UTC))
    assert "SUMMARY:Séance \\; IA\\, santé \\\\ imagerie\r\n" in body
    assert "\\n" in body
    assert all(len(line.encode()) <= 75 for line in body.split("\r\n"))
    assert "\r\n " in body  # ligne longue pliée
