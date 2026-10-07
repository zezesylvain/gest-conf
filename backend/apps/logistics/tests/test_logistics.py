"""Logistique (plan L8, N6 à N9) : fiches de venue, régimes (RG-23), repas, bénévoles."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import Notification, NotificationKind
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.logistics.models import DietaryDeclaration, SpeakerVisit
from apps.logistics.services import dietary, meals, shifts, visits
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_category, make_registration

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


def as_user(user) -> Actor:
    return Actor(kind=ActorKind.USER, user=user)


@pytest.fixture
def edition():
    return EditionFactory(
        timezone="Africa/Abidjan",
        start_date=dt.date(2027, 6, 1),
        end_date=dt.date(2027, 6, 3),
    )


def confirmed(edition, **fields):
    from apps.accounts.tests.factories import VerifiedUserFactory

    user = VerifiedUserFactory()
    make_registration(edition, user, status=RegistrationStatus.CONFIRMED, **fields)
    return user


# --- RG-23 : régimes ------------------------------------------------------------------------


def test_rg23_dietary_requires_explicit_consent_and_an_eligible_person(edition):
    participant = confirmed(edition)
    with pytest.raises(Invalid) as error:
        dietary.declare(
            edition, participant, diets=["vegan"], allergies="", consent=False, actor=COMMAND
        )
    assert "consent" in error.value.fields
    stranger = make_member(EditionFactory(), Role.CHAIR)
    with pytest.raises(Invalid):
        dietary.declare(
            edition, stranger, diets=["vegan"], allergies="", consent=True, actor=COMMAND
        )
    with pytest.raises(Invalid):
        dietary.declare(
            edition, participant, diets=["carnivore"], allergies="", consent=True, actor=COMMAND
        )
    declaration = dietary.declare(
        edition,
        participant,
        diets=["vegan", "gluten_free", "vegan"],
        allergies=" Arachides ",
        consent=True,
        actor=COMMAND,
    )
    assert (declaration.diets, declaration.allergies) == (["gluten_free", "vegan"], "Arachides")
    assert declaration.consented_at is not None


def test_rg23_dietary_content_never_enters_the_audit_log_and_withdrawal_erases(edition):
    participant = confirmed(edition)
    dietary.declare(
        edition,
        participant,
        diets=["no_pork"],
        allergies="Arachides",
        consent=True,
        actor=as_user(participant),
    )
    dietary.withdraw(edition, participant, actor=as_user(participant))
    assert not DietaryDeclaration.objects.exists()
    entries = AuditLog.objects.filter(action__startswith="dietary.")
    assert [entry.action for entry in entries.order_by("id")] == [
        "dietary.declared",
        "dietary.withdrawn",
    ]
    text = str([(entry.before, entry.after) for entry in entries])
    assert "no_pork" not in text and "Arachides" not in text


def test_rg23_aggregates_for_catering_names_only_in_a_reauthenticated_export(edition):
    logistics = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.LOGISTICS)
    program = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.PROGRAM)
    for diets, allergies in ((["vegan"], ""), (["vegan", "gluten_free"], "Lait")):
        dietary.declare(
            edition,
            confirmed(edition),
            diets=diets,
            allergies=allergies,
            consent=True,
            actor=COMMAND,
        )
    summary = dietary.summary(edition)
    assert summary["declarations"] == 2 and summary["allergies"] == 1
    assert summary["by_diet"]["vegan"] == 2 and summary["by_diet"]["gluten_free"] == 1
    base = f"/v1/manage/editions/{edition.pk}/logistics/dietary"
    assert client_for(logistics).get(base).json()["by_diet"]["vegan"] == 2
    # Le CO « programme » n'y a pas accès ; l'export nominatif exige une réauthentification.
    assert client_for(program).get(base).status_code == 403
    response = client_for(logistics, recent_auth=False).get(f"{base}/export")
    assert response.json()["code"] == "reauthentication_required"
    response = client_for(logistics).get(f"{base}/export")
    assert response.status_code == 200 and "Lait" in response.content.decode()
    assert AuditLog.objects.filter(action="dietary.exported").count() == 1


def test_rg23_declarations_and_visits_erased_30_days_after_the_edition(edition):
    participant = confirmed(edition)
    dietary.declare(
        edition, participant, diets=["vegan"], allergies="", consent=True, actor=COMMAND
    )
    speaker = make_member(edition, Role.SPEAKER)
    visits.update_by_staff(edition, speaker, {"hotel": "Ivoire"}, actor=COMMAND)
    ongoing = EditionFactory(end_date=dt.date(2027, 6, 3))
    other = confirmed(ongoing)
    dietary.declare(ongoing, other, diets=["vegan"], allergies="", consent=True, actor=COMMAND)
    now = timezone.make_aware(dt.datetime(2027, 7, 1))  # 28 jours après la fin
    assert dietary.erase_after_edition(dry_run=False, now=now) == 0
    later = timezone.make_aware(dt.datetime(2027, 7, 10))
    assert dietary.erase_after_edition(dry_run=True, now=later) == 2
    assert dietary.erase_after_edition(dry_run=False, now=later) == 2
    assert visits.erase_after_edition(dry_run=False, now=later) == 1
    assert not DietaryDeclaration.objects.exists() and not SpeakerVisit.objects.exists()


def test_rg23_my_dietary_api(edition):
    participant = confirmed(edition)
    url = f"/v1/me/editions/{edition.pk}/dietary"
    client = client_for(participant)
    assert client.get(url).json() == {
        "eligible": True,
        "diets": [],
        "allergies": "",
        "consented_at": None,
    }
    response = client.put(url, {"diets": ["vegetarian"], "consent": False}, format="json")
    assert response.status_code == 400
    response = client.put(url, {"diets": ["vegetarian"], "consent": True}, format="json")
    assert response.json()["diets"] == ["vegetarian"]
    assert client.delete(url).json()["consented_at"] is None


# --- N6 : fiches de venue -------------------------------------------------------------------


def test_n6_speaker_writes_his_part_only_in_local_time_and_never_sees_the_internal_note(edition):
    speaker = make_member(edition, Role.SPEAKER)
    visits.update_by_staff(
        edition, speaker, {"internal_note": "Budget serré", "hotel": "Ivoire"}, actor=COMMAND
    )
    url = f"/v1/me/editions/{edition.pk}/visit"
    client = client_for(speaker)
    response = client.put(
        url,
        {
            "technical_needs": ["projector", "microphone"],
            "arrival_local": "2027-05-31T18:30",
            "arrival_means": "plane",
            "arrival_reference": "AF702",
            "departure_local": "2027-06-04T09:00",
            # Champs du CO : ignorés.
            "internal_note": "Piratage",
            "hotel": "Autre",
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert "internal_note" not in body
    assert (body["hotel"], body["arrival_local"]) == ("Ivoire", "2027-05-31T18:30")
    visit = SpeakerVisit.objects.get()
    assert visit.internal_note == "Budget serré"
    # Abidjan : UTC+0.
    assert visit.arrival_at == dt.datetime(2027, 5, 31, 18, 30, tzinfo=dt.UTC)
    response = client.put(url, {"departure_local": "2027-05-30T09:00"}, format="json")
    assert response.status_code == 400
    # Le journal ne garde que les noms des champs changés.
    entry = AuditLog.objects.filter(action="visit.updated").last()
    assert "AF702" not in str(entry.after)


def test_n6_only_invited_speakers_have_a_visit(edition):
    author = make_member(edition, Role.AUTHOR)
    response = client_for(author).get(f"/v1/me/editions/{edition.pk}/visit")
    assert response.status_code == 404
    with pytest.raises(Invalid):
        visits.update_by_staff(edition, author, {"hotel": "Ivoire"}, actor=COMMAND)


def test_n6_missing_equipment_is_read_in_the_published_programme(edition):
    from apps.program.models import ProgramPublication, Room, Session, Slot
    from apps.program.services.publication import build_snapshot

    speaker = make_member(edition, Role.SPEAKER)
    visits.update_by_staff(
        edition, speaker, {"technical_needs": ["projector", "interpretation"]}, actor=COMMAND
    )
    room = Room.objects.create(edition=edition, name="Amphi", equipment=["projector"])
    start = dt.datetime(2027, 6, 1, 9, tzinfo=dt.UTC)
    session = Session.objects.create(
        edition=edition,
        kind="keynote",
        title_fr="Conférence invitée",
        room=room,
        starts_at=start,
        ends_at=start + dt.timedelta(hours=1),
    )
    Slot.objects.create(
        session=session,
        position=0,
        duration_min=45,
        title_fr="Ouverture",
        speaker=speaker,
        starts_at=start,
        ends_at=start + dt.timedelta(minutes=45),
    )
    assert visits.missing_equipment(edition) == {}  # rien de publié
    ProgramPublication.objects.create(
        edition=edition,
        version=1,
        revision=0,
        published_at=timezone.now(),
        snapshot=build_snapshot(edition, [session]),
    )
    assert visits.missing_equipment(edition) == {speaker.pk: ["interpretation"]}


# --- N8 : repas -------------------------------------------------------------------------------


def test_n8_meal_estimate_counts_each_person_once_with_diets_and_margin(edition):
    from apps.registrations.models import RegistrationOption

    category = make_category(edition, "chercheur")
    dinner = RegistrationOption.objects.create(edition=edition, code="diner", label_fr="Dîner")
    with_dinner = confirmed(edition, category=category)
    with_dinner.registrations.get().options.add(dinner)
    confirmed(edition, category=category)
    speaker = make_member(edition, Role.SPEAKER)
    chair = make_member(edition, Role.CHAIR)
    make_registration(edition, chair, status=RegistrationStatus.CONFIRMED, category=category)
    make_member(edition, Role.VOLUNTEER)
    dietary.declare(
        edition, speaker, diets=["vegan"], allergies="Lait", consent=True, actor=COMMAND
    )
    lunch = meals.create_meal(
        edition,
        {
            "day": dt.date(2027, 6, 1),
            "kind": "lunch",
            "include_committees": True,
            "margin_percent": 10,
        },
        actor=COMMAND,
    )
    estimate = meals.estimate(lunch)
    # 3 inscrits (dont le Chair, compté une fois), l'intervenant, le Chair : 4 personnes.
    assert (estimate["count"], estimate["margin"], estimate["total"]) == (4, 1, 5)
    assert estimate["by_diet"]["vegan"] == 1 and estimate["allergies"] == 1
    gala = meals.create_meal(
        edition,
        {
            "day": dt.date(2027, 6, 2),
            "kind": "dinner",
            "option_code": "diner",
            "include_speakers": False,
            "margin_percent": 0,
        },
        actor=COMMAND,
    )
    assert meals.estimate(gala)["count"] == 1
    with pytest.raises(Invalid):
        meals.create_meal(edition, {"day": dt.date(2027, 7, 1), "kind": "lunch"}, actor=COMMAND)
    with pytest.raises(Invalid):
        meals.create_meal(
            edition,
            {"day": dt.date(2027, 6, 1), "kind": "lunch", "option_code": "x"},
            actor=COMMAND,
        )
    header, rows = meals.export_rows(edition)
    assert "Effectif" in header and len(rows) == 2
    # Aucune donnée nominative dans la commande au traiteur.
    assert speaker.email not in str(rows)


# --- N9 : bénévoles ----------------------------------------------------------------------------


def shift(edition, start_hour, end_hour, title="Accueil"):
    return shifts.create_shift(
        edition,
        {
            "title_fr": title,
            "starts_local": dt.datetime(2027, 6, 1, start_hour),
            "ends_local": dt.datetime(2027, 6, 1, end_hour),
            "needed": 2,
        },
        actor=COMMAND,
    )


def test_n9_overlapping_shifts_are_refused_for_the_same_volunteer(edition):
    volunteer = make_member(edition, Role.VOLUNTEER)
    morning = shift(edition, 8, 12)
    overlapping = shift(edition, 11, 14, "Vestiaire")
    afternoon = shift(edition, 14, 18, "Salle B")
    shifts.assign(morning, volunteer.pk, actor=COMMAND)
    shifts.assign(morning, volunteer.pk, actor=COMMAND)  # sans effet
    assert morning.assignments.count() == 1
    with pytest.raises(RuleViolation) as error:
        shifts.assign(overlapping, volunteer.pk, actor=COMMAND)
    assert error.value.code == "shift_overlap"
    shifts.assign(afternoon, volunteer.pk, actor=COMMAND)
    # Déplacer un poste sur un autre du même bénévole est refusé aussi.
    with pytest.raises(RuleViolation):
        shifts.update_shift(afternoon, {"starts_local": dt.datetime(2027, 6, 1, 10)}, actor=COMMAND)
    author = make_member(edition, Role.AUTHOR)
    with pytest.raises(Invalid):
        shifts.assign(afternoon, author.pk, actor=COMMAND)
    assert (
        Notification.objects.filter(user=volunteer, kind=NotificationKind.SHIFT_ASSIGNED).count()
        == 2
    )
    shifts.unassign(morning, volunteer.pk, actor=COMMAND)
    shifts.unassign(morning, volunteer.pk, actor=COMMAND)  # sans effet
    assert [item.title_fr for item in shifts.my_shifts(edition, volunteer)] == ["Salle B"]
    # Retrait signalé à la cloche, y compris par la suppression d'un poste pourvu.
    shifts.delete_shift(afternoon, actor=COMMAND)
    removed = Notification.objects.filter(user=volunteer, kind=NotificationKind.SHIFT_REMOVED)
    assert sorted(item.payload["title"] for item in removed) == ["Accueil", "Salle B"]
    assert shifts.my_shifts(edition, volunteer) == []


def test_n9_my_planning_and_calendar_for_the_volunteer_only(edition):
    volunteer = make_member(edition, Role.VOLUNTEER)
    accueil = shift(edition, 8, 12)
    shifts.assign(accueil, volunteer.pk, actor=COMMAND)
    base = f"/v1/manage/editions/{edition.pk}/me/shifts"
    client = client_for(volunteer)
    body = client.get(base).json()
    assert [(item["title_fr"], item["starts_local"]) for item in body] == [
        ("Accueil", "2027-06-01T08:00")
    ]
    calendar = client.get(f"{base}/calendar")
    assert calendar["Content-Type"].startswith("text/calendar")
    assert "SUMMARY" in calendar.content.decode()
    coordinator = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.VOLUNTEERS)
    assert client_for(coordinator).get(base).status_code == 403
    board = client_for(coordinator).get(f"/v1/manage/editions/{edition.pk}/logistics/shifts")
    assert board.json()["shifts"][0]["missing"] == 1


def test_n9_archived_edition_refuses_planning_changes(edition):
    morning = shift(edition, 8, 12)
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    with pytest.raises(RuleViolation):
        shifts.update_shift(morning, {"needed": 3}, actor=COMMAND)
