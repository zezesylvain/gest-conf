"""Envoi par la file (plan L1 §8.3 « Gestionnaire d'envoi », §12.1 « E-mails »)."""

import time
from datetime import timedelta

import pytest
from django.core import mail
from django.core.mail.backends.locmem import EmailBackend
from django.utils import timezone

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import (
    purge_old_bodies,
    purge_unsent_sensitive_bodies,
    queue_email,
)
from apps.core import jobs
from apps.core.models import Job, JobStatus

from .conftest import PLAIN, SENSITIVE

pytestmark = pytest.mark.django_db


def run_queue() -> int:
    return jobs.run_pending(deadline=time.monotonic() + 30)


class FailingBackend(EmailBackend):
    def send_messages(self, messages):
        raise ConnectionError("fournisseur injoignable pour jeanne@univ.ci")


def test_cron_sends_email_with_traceable_message_id():
    email = queue_email(
        template_code=PLAIN, to_email="jeanne@univ.ci", context={"display_name": "J"}
    )
    assert run_queue() == 1
    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["jeanne@univ.ci"]
    assert message.subject == "[GEST-CONF] Message ordinaire"
    assert message.from_email == "GEST-CONF <no-reply@conference.test>"
    assert message.extra_headers["Message-ID"].startswith(f"<gestconf.outbox.{email.pk}.")
    assert message.extra_headers["Message-ID"].endswith("@conference.test>")
    email.refresh_from_db()
    assert email.status == OutboxStatus.SENT
    assert email.sent_at is not None
    assert email.attempts == 1
    # Corps ordinaire conservé (purge à 30 jours, D15).
    assert "Bonjour J" in email.body_text
    assert email.purged_at is None


def test_sensitive_body_is_purged_after_sending():
    email = queue_email(
        template_code=SENSITIVE, to_email="a@b.org", context={"activate_url": "https://x/#cle"}
    )
    run_queue()
    assert "https://x/#cle" in mail.outbox[0].body
    email.refresh_from_db()
    assert (email.body_text, email.body_html) == ("", "")
    assert email.purged_at is not None
    assert email.subject  # l'objet reste (métadonnées d'envoi)


def test_send_handler_is_idempotent():
    email = queue_email(template_code=PLAIN, to_email="a@b.org")
    run_queue()
    job = Job.objects.get(dedup_key=f"email:{email.pk}")
    # Rejeu du gestionnaire (livraison « au moins une fois ») : aucun second envoi.
    from apps.communications.jobs import send_email

    send_email(job)
    assert len(mail.outbox) == 1


def test_failed_send_is_retried_then_marked_failed(settings):
    settings.EMAIL_BACKEND = "apps.communications.tests.test_send.FailingBackend"
    email = queue_email(template_code=PLAIN, to_email="jeanne@univ.ci")
    job = Job.objects.get(dedup_key=f"email:{email.pk}")
    Job.objects.filter(pk=job.pk).update(max_attempts=2)

    run_queue()
    email.refresh_from_db()
    job.refresh_from_db()
    assert email.status == OutboxStatus.QUEUED
    assert email.last_error == "builtins.ConnectionError"
    assert "jeanne" not in email.last_error + job.last_error
    assert job.status == JobStatus.PENDING

    Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
    run_queue()
    email.refresh_from_db()
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert email.status == OutboxStatus.FAILED
    assert email.attempts == 2


def test_hourly_cap_defers_without_consuming_attempts(settings):
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 1
    first = queue_email(template_code=PLAIN, to_email="a@b.org")
    second = queue_email(template_code=PLAIN, to_email="c@d.org")
    run_queue()
    assert len(mail.outbox) == 1
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.status == OutboxStatus.SENT
    assert second.status == OutboxStatus.QUEUED
    job = Job.objects.get(dedup_key=f"email:{second.pk}")
    assert job.status == JobStatus.PENDING
    assert job.attempts == 0
    assert job.run_at > timezone.now() + timedelta(minutes=59)


def test_unsent_sensitive_body_purged_after_24_hours_and_never_sent():
    email = queue_email(template_code=SENSITIVE, to_email="a@b.org", context={"activate_url": "u"})
    now = timezone.now()
    OutboxEmail.objects.filter(pk=email.pk).update(created_at=now - timedelta(hours=25))
    assert purge_unsent_sensitive_bodies(True, now) == 1
    assert purge_unsent_sensitive_bodies(False, now) == 1
    email.refresh_from_db()
    assert email.body_text == ""
    run_queue()
    assert mail.outbox == []
    email.refresh_from_db()
    assert email.status == OutboxStatus.FAILED


def test_old_bodies_purged_only_when_applied():
    email = queue_email(template_code=PLAIN, to_email="a@b.org")
    run_queue()
    now = timezone.now()
    OutboxEmail.objects.filter(pk=email.pk).update(created_at=now - timedelta(days=31))
    assert purge_old_bodies(True, now) == 1
    email.refresh_from_db()
    assert email.body_text != ""
    assert purge_old_bodies(False, now) == 1
    email.refresh_from_db()
    assert email.body_text == ""
    assert email.purged_at is not None
