"""Questionnaires de satisfaction (plan L8, N12 ; RG-21)."""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import Notification, NotificationKind, OutboxEmail
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog, Job
from apps.events.tests.certificate_helpers import present
from apps.surveys import services
from apps.surveys.models import Survey, SurveyInvitation, SurveyResponse, SurveyStatus

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    """Édition en cours (Abidjan, UTC) : la veille au lendemain."""
    today = timezone.localdate()
    return EditionFactory(
        timezone="Africa/Abidjan",
        start_date=today - dt.timedelta(days=1),
        end_date=today + dt.timedelta(days=1),
    )


def local(delta: dt.timedelta) -> dt.datetime:
    """Heure locale d'Abidjan (UTC), sans fuseau, décalée de maintenant."""
    return (timezone.now() + delta).astimezone(dt.UTC).replace(tzinfo=None, second=0, microsecond=0)


def open_survey(edition, people: int = 0, **fields):
    attendees = [present(edition).user for _index in range(people)]
    survey = services.create_survey(
        edition,
        {
            "title_fr": "Votre avis",
            "opens_local": local(-dt.timedelta(hours=1)),
            "closes_local": local(dt.timedelta(days=6)),
            **fields,
        },
        actor=COMMAND,
    )
    services.publish(survey, actor=COMMAND)
    while services.invite_batch(survey.pk):
        pass
    survey.refresh_from_db()
    return survey, attendees


def full_answers(survey, note=4, comment="Très bien"):
    answers = {}
    for question in survey.questions.all():
        answers[str(question.pk)] = comment if question.kind == "text" else note
    return answers


def test_n12_default_template_and_publication_schedules_invitation_and_one_reminder(edition):
    survey = services.create_survey(
        edition,
        {
            "title_fr": "Votre avis",
            "opens_local": local(dt.timedelta(days=1)),
            "closes_local": local(dt.timedelta(days=9)),
        },
        actor=COMMAND,
    )
    kinds = list(survey.questions.values_list("kind", flat=True))
    assert kinds == ["rating"] * 5 + ["text"]
    services.publish(survey, actor=COMMAND)
    invite = Job.objects.get(kind=services.INVITE_JOB)
    remind = Job.objects.get(kind=services.REMIND_JOB)
    assert invite.run_at == survey.opens_at
    assert remind.run_at == survey.opens_at + (survey.closes_at - survey.opens_at) / 2
    # Pas encore ouvert : la tâche d'invitation ne fait rien.
    assert services.invite_batch(survey.pk) is False
    assert not SurveyInvitation.objects.exists()
    with pytest.raises(RuleViolation):
        services.publish(survey, actor=COMMAND)
    with pytest.raises(Invalid):
        services.update_survey(survey, {"opens_local": local(dt.timedelta(days=2))}, actor=COMMAND)


def test_n12_present_people_are_invited_by_bell_and_email_once_and_reminded_once(edition):
    survey, attendees = open_survey(edition, people=3)
    assert SurveyInvitation.objects.filter(survey=survey).count() == 3
    assert Notification.objects.filter(kind=NotificationKind.SURVEY_INVITATION).count() == 3
    invitations = OutboxEmail.objects.filter(template_code=services.INVITATION_TEMPLATE)
    assert invitations.count() == 3 and all(email.is_bulk for email in invitations)
    assert "anonymes" in invitations.first().body_text
    assert services.invite_batch(survey.pk) is False  # déjà fait : sans effet
    services.answer(survey, attendees[0], full_answers(survey))
    services.remind_batch(survey.pk)
    reminders = OutboxEmail.objects.filter(template_code=services.REMINDER_TEMPLATE)
    assert sorted(reminders.values_list("to_user_id", flat=True)) == sorted(
        user.pk for user in attendees[1:]
    )
    services.remind_batch(survey.pk)  # une seule relance
    assert reminders.count() == 2


def test_n12_session_survey_invites_only_people_checked_in_at_the_session(edition):
    from apps.program.services import planning
    from apps.program.tests.helpers import COMMAND as PLANNER

    start = timezone.now() - dt.timedelta(hours=3)
    session = planning.create_session(
        edition,
        {
            "kind": "parallel",
            "title_fr": "Santé",
            "starts_local": start.astimezone(dt.UTC).replace(tzinfo=None, second=0, microsecond=0),
            "ends_local": (start + dt.timedelta(hours=1))
            .astimezone(dt.UTC)
            .replace(tzinfo=None, second=0, microsecond=0),
        },
        actor=PLANNER,
    )
    inside = present(edition, session=session).user
    present(edition)  # accueil seulement
    _survey, _people = open_survey(edition, scope="session", session=session.pk)
    assert list(SurveyInvitation.objects.values_list("user_id", flat=True)) == [inside.pk]


def test_rg21_response_is_stored_without_any_link_to_the_person(edition):
    """RG-21 : ni compte, ni invitation, ni date sur la réponse ; clé aléatoire ; rien au
    journal ; l'invitation n'est marquée « répondu » qu'au jour près."""
    survey, (first, _second) = open_survey(edition, people=2)
    services.answer(survey, first, full_answers(survey, comment="Merci"))
    response = SurveyResponse.objects.get()
    field_names = {field.name for field in SurveyResponse._meta.get_fields()}
    assert field_names == {"id", "survey", "answers"}
    assert response.pk.version == 4
    invitation = SurveyInvitation.objects.get(user=first)
    assert invitation.answered_on == timezone.localdate()
    assert {field.name for field in SurveyInvitation._meta.get_fields()} == {
        "id",
        "survey",
        "user",
        "invited_on",
        "reminded_on",
        "answered_on",
    }
    # Le journal ne relie personne à la réponse.
    assert not AuditLog.objects.filter(action__startswith="survey.answer").exists()
    assert not AuditLog.objects.filter(object_id=str(response.pk)).exists()
    # Aucune colonne de la table des réponses ne contient le compte.
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT * FROM {SurveyResponse._meta.db_table}")  # noqa: S608
        columns = [column[0] for column in cursor.description]
    assert set(columns) == {"id", "survey_id", "answers"}
    with pytest.raises(RuleViolation) as error:
        services.answer(survey, first, full_answers(survey))
    assert error.value.code == "survey_answered"
    stranger = make_member(edition, Role.ATTENDEE)
    with pytest.raises(RuleViolation):
        services.answer(survey, stranger, full_answers(survey))


def test_n12_answers_are_validated_and_lock_the_questions(edition):
    survey, (person, _other) = open_survey(edition, people=2)
    rating = survey.questions.filter(kind="rating").first()
    with pytest.raises(Invalid) as error:
        services.answer(survey, person, {str(rating.pk): 9})
    assert str(rating.pk) in error.value.fields
    with pytest.raises(Invalid):
        services.answer(survey, person, {"999999": 3})
    services.answer(survey, person, full_answers(survey))
    survey.refresh_from_db()
    assert survey.locked_at is not None
    with pytest.raises(RuleViolation) as error:
        services.add_question(survey, {"kind": "text", "label_fr": "Autre"}, actor=COMMAND)
    assert error.value.code == "survey_locked"
    copy = services.duplicate(survey, actor=COMMAND)
    assert copy.status == SurveyStatus.DRAFT and copy.locked_at is None
    assert copy.questions.count() == survey.questions.count()
    services.add_question(
        copy,
        {
            "kind": "single",
            "label_fr": "Format préféré",
            "choices": [{"label_fr": "Présentiel"}, {"label_fr": "Hybride"}],
        },
        actor=COMMAND,
    )


def test_n12_closed_survey_refuses_answers(edition):
    survey, (person,) = open_survey(edition, people=1)
    Survey.objects.filter(pk=survey.pk).update(closes_at=timezone.now() - dt.timedelta(minutes=1))
    survey.refresh_from_db()
    with pytest.raises(RuleViolation) as error:
        services.answer(survey, person, full_answers(survey))
    assert error.value.code == "survey_not_open"


def test_n12_results_are_hidden_below_five_responses_and_texts_are_shuffled(edition):
    survey, people = open_survey(edition, people=6)
    for index, person in enumerate(people[:4]):
        services.answer(
            survey, person, full_answers(survey, note=index + 1, comment=f"Texte {index}")
        )
    hidden = services.results(survey)
    assert (hidden["responses"], hidden["questions"]) == (4, [])
    with pytest.raises(RuleViolation) as error:
        services.export_rows(survey)
    assert error.value.code == "survey_threshold"
    services.answer(survey, people[4], full_answers(survey, note=5, comment="Texte 4"))
    data = services.results(survey)
    first = data["questions"][0]
    assert first["average"] == Decimal("3.00")  # notes 1 à 5
    assert [count["count"] for count in first["counts"]] == [1, 1, 1, 1, 1]
    assert data["invited"] == 6 and data["answered"] == 5
    # Graines fixes : deux mélanges reproductibles et différents (S311 sans objet ici).
    _header, rows = services.export_rows(survey, shuffle=random.Random(1))  # noqa: S311
    texts = [row[1] for row in rows if str(row[1]).startswith("Texte")]
    assert sorted(texts) == [f"Texte {index}" for index in range(5)]
    _header, again = services.export_rows(survey, shuffle=random.Random(2))  # noqa: S311
    assert [row[1] for row in again if str(row[1]).startswith("Texte")] != texts


def test_n12_api_for_the_person_and_for_the_committee(edition):
    survey, (person, _other) = open_survey(edition, people=2)
    client = client_for(person)
    mine = client.get("/v1/me/surveys").json()
    assert [(item["id"], item["is_open"], item["answered"]) for item in mine] == [
        (survey.pk, True, False)
    ]
    detail = client.get(f"/v1/me/surveys/{survey.pk}").json()
    assert len(detail["questions"]) == 6
    response = client.post(
        f"/v1/me/surveys/{survey.pk}", {"answers": full_answers(survey)}, format="json"
    )
    assert response.status_code == 200 and response.json()["answered"] is True
    outsider = make_member(edition, Role.ATTENDEE)
    assert client_for(outsider).get(f"/v1/me/surveys/{survey.pk}").status_code == 404
    secretariat = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.SECRETARIAT)
    manage = client_for(secretariat)
    base = f"/v1/manage/editions/{edition.pk}/surveys"
    assert manage.get(base).json()[0]["stats"]["answered"] == 1
    results = manage.get(f"{base}/{survey.pk}/results").json()
    assert results["questions"] == [] and results["threshold"] == 5
    logistics = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.LOGISTICS)
    assert client_for(logistics).get(base).status_code == 403


def test_n15_invitations_are_exported_responses_are_not(edition):
    from apps.core.personal_data import export_sections

    survey, (person,) = open_survey(edition, people=1)
    services.answer(survey, person, full_answers(survey, comment="Mon avis personnel"))
    data = export_sections(person)
    assert data["survey_invitations"][0]["answered_on"] == timezone.localdate().isoformat()
    assert "Mon avis personnel" not in str(data)
