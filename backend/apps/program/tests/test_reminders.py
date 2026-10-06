"""Rappels de la confirmation de présentation (plan L5, §9 ; commande ``remind_presentations``)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command

from apps.communications.models import OutboxEmail
from apps.conferences.models import Edition, EditionStatus
from apps.program.services.reminders import remind_presentations
from apps.program.tests.helpers import confirmed, edition
from apps.reviews.tests.helpers import in_status
from apps.submissions.models import StatusHistory
from apps.submissions.models import SubmissionStatus as S

pytestmark = pytest.mark.django_db

RECEIVED = dt.datetime(2027, 4, 1, 10, 0, tzinfo=dt.UTC)


def final_received(current, *, at=RECEIVED):
    """Version finale reçue à ``at`` (historique écrit comme le ferait le workflow)."""
    submission = in_status(confirmed(current), S.CAMERA_READY_RECEIVED)
    StatusHistory.objects.create(
        submission=submission,
        from_status=S.ACCEPTED,
        to_status=S.CAMERA_READY_RECEIVED,
        actor_label="test",
        at=at,
    )
    return submission


def reminders(submission) -> list[str]:
    return list(
        OutboxEmail.objects.filter(
            idempotency_key__startswith=f"program-presentation-reminder:{submission.pk}:"
        )
        .order_by("id")
        .values_list("idempotency_key", flat=True)
    )


def test_reminder_three_then_ten_days_after_the_final_version_once_each():
    current = edition()
    submission = final_received(current)
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=2)) == 0
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=3, hours=1)) == 1
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=4)) == 0  # idempotente
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=10, hours=1)) == 1
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=30)) == 0
    assert [key.rsplit(":", 1)[1] for key in reminders(submission)] == ["d3", "d10"]
    email = OutboxEmail.objects.filter(template_code="program/email/presentation_reminder").first()
    assert email.to_email == submission.submitter.email
    assert f"/compte/soumissions/{submission.pk}" in email.body_text
    assert submission.reference in email.body_text


def test_missed_run_sends_only_the_latest_reminder():
    current = edition()
    submission = final_received(current)
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=12)) == 1
    assert [key.rsplit(":", 1)[1] for key in reminders(submission)] == ["d10"]


def test_no_reminder_once_confirmed_or_in_an_archived_edition():
    current = edition()
    done = final_received(current)
    in_status(done, S.CONFIRMED)
    archived = edition()
    late = final_received(archived)
    Edition.objects.filter(pk=archived.pk).update(status=EditionStatus.ARCHIVED)
    assert remind_presentations(now=RECEIVED + dt.timedelta(days=5)) == 0
    assert reminders(done) == reminders(late) == []


def test_command_is_locked_and_reports():
    final_received(edition(), at=dt.datetime.now(tz=dt.UTC) - dt.timedelta(days=4))
    call_command("remind_presentations", verbosity=0)
    assert (
        OutboxEmail.objects.filter(template_code="program/email/presentation_reminder").count() == 1
    )
