"""Récapitulatif quotidien des tâches (plan L8, N3) : ``remind_tasks``."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import make_member
from apps.communications.models import OutboxEmail
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.logistics.models import Task, TaskStatus
from apps.logistics.services.reminders import remind_tasks

pytestmark = pytest.mark.django_db

# 7 octobre 2027, 23 h 30 UTC : déjà le 8 octobre à Paris, encore le 7 à Abidjan.
NOW = dt.datetime(2027, 10, 7, 23, 30, tzinfo=dt.UTC)


def task(edition, assignee, title, due, **fields):
    return Task.objects.create(
        edition=edition, title=title, assignee=assignee, due_date=due, **fields
    )


def test_n3_one_digest_per_assignee_and_edition_per_day():
    edition = EditionFactory(timezone="Africa/Abidjan")
    member = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.LOGISTICS)
    today = dt.date(2027, 10, 7)
    task(edition, member, "En retard", today - dt.timedelta(days=3))
    task(edition, member, "Demain", today + dt.timedelta(days=1))
    task(edition, member, "Plus tard", today + dt.timedelta(days=5))
    task(edition, member, "Faite", today, status=TaskStatus.DONE)
    task(edition, member, "Archivée", today, archived_at=NOW)
    assert remind_tasks(now=NOW) == 1
    email = OutboxEmail.objects.get(to_user=member)
    assert "En retard : en retard" in email.body_text
    assert "Demain : échéance" in email.body_text
    assert "Plus tard" not in email.body_text and "Faite" not in email.body_text
    assert f"/gestion/editions/{edition.pk}/organisation/taches" in email.body_text
    assert set(Task.objects.filter(reminded_on=today).values_list("title", flat=True)) == {
        "En retard",
        "Demain",
    }
    # Même jour : rien de plus (idempotente) ; le lendemain : nouveau récapitulatif.
    assert remind_tasks(now=NOW) == 0
    assert remind_tasks(now=NOW + dt.timedelta(days=1)) == 1


def test_n3_today_is_read_in_the_edition_time_zone():
    edition = EditionFactory(timezone="Europe/Paris")
    member = make_member(edition, Role.CHAIR)
    # À Paris on est déjà le 8 : une échéance au 10 tombe dans les deux jours.
    task(edition, member, "Le 10", dt.date(2027, 10, 10))
    assert remind_tasks(now=NOW) == 1


def test_n3_no_digest_for_archived_editions_or_inactive_accounts():
    archived = EditionFactory(status=EditionStatus.ARCHIVED)
    member = make_member(archived, Role.CHAIR)
    task(archived, member, "A", dt.date(2027, 10, 1))
    edition = EditionFactory()
    inactive = make_member(edition, Role.CHAIR, is_active=False)
    task(edition, inactive, "B", dt.date(2027, 10, 1))
    assert remind_tasks(now=NOW) == 0


def test_n3_remind_tasks_command_is_locked_and_counts(capsys):
    edition = EditionFactory()
    member = make_member(edition, Role.CHAIR)
    task(edition, member, "A", dt.date(2000, 1, 1))
    call_command("remind_tasks")
    assert "remind_tasks : 1 récapitulatif(s)" in capsys.readouterr().out
