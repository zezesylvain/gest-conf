"""Lot L4, étape L4.2 : relances des relecteurs (H15), commande ``remind_reviewers``."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import make_member
from apps.communications.models import OutboxEmail
from apps.conferences.models import EditionStatus
from apps.core.actor import Actor
from apps.core.models import CronHeartbeat
from apps.reviews.models import Review, ReviewAssignment, ReviewStatus
from apps.reviews.services import assignments
from apps.reviews.services.grids import create_grid
from apps.reviews.services.reminders import due_reminder, remind_reviewers
from apps.reviews.tests.helpers import in_status, reviewer, screening_submission
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import user_actor

pytestmark = pytest.mark.django_db

NOW = dt.datetime(2099, 3, 1, 12, tzinfo=dt.UTC)
DAY = dt.timedelta(days=1)


def assignment_due(due: dt.datetime, *, assigned: dt.datetime = NOW - 30 * DAY, **fields):
    return ReviewAssignment(due_at=due, assigned_at=assigned, reminders=[], **fields)


@pytest.mark.parametrize(
    ("due", "expected"),
    [
        (NOW + 10 * DAY, None),
        (NOW + 7 * DAY, "j7"),
        (NOW + 2 * DAY, "j7"),
        (NOW + DAY, "j1"),
        (NOW + dt.timedelta(hours=3), "j1"),
        (NOW, "late"),
        (NOW - 5 * DAY, "late"),
    ],
)
def test_h15_reminder_windows(due, expected):
    assert due_reminder(assignment_due(due), NOW) == expected


def test_h15_reminders_are_sent_once_each_and_not_inside_the_assignment_window():
    sent = assignment_due(NOW + 2 * DAY)
    sent.reminders = ["j7"]
    assert due_reminder(sent, NOW) is None
    # Affecté trois jours avant l'échéance : l'e-mail d'affectation tient lieu de J-7.
    recent = assignment_due(NOW + 2 * DAY, assigned=NOW - DAY)
    assert due_reminder(recent, NOW) is None
    assert due_reminder(recent, NOW + 1.5 * DAY) == "j1"
    assert due_reminder(assignment_due(None), NOW) is None


def _assignment(submission, user, *, due: dt.datetime):
    actor = user_actor(make_member(submission.edition, Role.SC_CHAIR))
    return assignments.assign(
        submission, user, actor=actor, due_local=due.replace(tzinfo=None), now=due - 40 * DAY
    )


def test_h15_remind_reviewers_is_idempotent_and_skips_finished_work():
    submission = in_status(screening_submission(), S.UNDER_REVIEW)
    edition = submission.edition
    edition.timezone = "UTC"
    edition.save()
    pending = _assignment(submission, reviewer(edition), due=NOW + 2 * DAY)
    done = _assignment(submission, reviewer(edition), due=NOW + 2 * DAY)
    Review.objects.create(
        assignment=done,
        grid=create_grid(edition, name="G", actor=Actor.command("cli:test")),
        status=ReviewStatus.SUBMITTED,
    )
    screening = screening_submission(edition)
    _assignment(screening, reviewer(edition), due=NOW + 2 * DAY)  # évaluation non ouverte
    OutboxEmail.objects.all().delete()

    assert remind_reviewers(now=NOW) == 1
    assert remind_reviewers(now=NOW) == 0
    pending.refresh_from_db()
    assert pending.reminders == ["j7"]
    (mail,) = OutboxEmail.objects.filter(template_code="review/email/reminder")
    assert mail.to_email == pending.reviewer.email
    assert "Mensah" not in mail.body_text  # RG-04
    assert remind_reviewers(now=NOW + 1.5 * DAY) == 1
    assert remind_reviewers(now=NOW + 3 * DAY) == 1
    assert remind_reviewers(now=NOW + 9 * DAY) == 0
    pending.refresh_from_db()
    assert pending.reminders == ["j7", "j1", "late"]
    late = OutboxEmail.objects.filter(template_code="review/email/reminder").last()
    assert "dépassée" in late.body_text


def test_h15_no_reminder_for_archived_editions_or_ended_assignments():
    submission = in_status(screening_submission(), S.UNDER_REVIEW)
    edition = submission.edition
    edition.timezone = "UTC"
    edition.save()
    cancelled = _assignment(submission, reviewer(edition), due=NOW + 2 * DAY)
    assignments.cancel_assignment(cancelled, reason="Remplacé", actor=Actor.command("cli:test"))
    other = in_status(screening_submission(), S.UNDER_REVIEW)
    other.edition.timezone = "UTC"
    other.edition.save()
    _assignment(other, reviewer(other.edition), due=NOW + 2 * DAY)
    other.edition.status = EditionStatus.ARCHIVED
    other.edition.save()
    assert remind_reviewers(now=NOW) == 0


def test_remind_reviewers_command_is_locked_and_reports():
    call_command("remind_reviewers", verbosity=0)
    assert CronHeartbeat.objects.filter(name="remind_reviewers").exists()
