"""Commandes send_test_email et outbox (plan L1 §9.4), parcours J-tech de bout en bout."""

from io import StringIO

import pytest
from django.core import mail
from django.core.management import CommandError, call_command

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import queue_email
from apps.core.models import AuditLog, Job, JobStatus

from .conftest import PLAIN

pytestmark = pytest.mark.django_db


def run(name, *args, **options):
    out = StringIO()
    call_command(name, *args, stdout=out, **options)
    return out.getvalue()


def test_send_test_email_is_queued_then_sent_by_the_cron():
    """J-tech (plan §13) : l'e-mail de test attend le passage du cron, qui l'envoie."""
    output = run("send_test_email", "ops@univ.ci", locale="en")
    assert "mis en file" in output
    assert mail.outbox == []
    email = OutboxEmail.objects.get()
    entry = AuditLog.objects.get(action="email.test_queued")
    assert entry.actor_label.startswith("cli:")
    assert entry.after == {"to": "o***@univ.ci", "locale": "en"}

    run("run_jobs")
    assert len(mail.outbox) == 1
    assert mail.outbox[0].subject == "[GEST-CONF] Test email"
    email.refresh_from_db()
    assert email.status == OutboxStatus.SENT


def test_send_test_email_validates_address():
    with pytest.raises(CommandError):
        run("send_test_email", "pas-une-adresse")


def test_outbox_lists_without_clear_address_or_body():
    queue_email(template_code=PLAIN, to_email="jeanne@univ.ci", context={"display_name": "J"})
    output = run("outbox", status="queued")
    assert "j***@univ.ci" in output
    assert "jeanne" not in output
    assert "Bonjour" not in output


def test_outbox_retry_requeues_failed_email_and_is_audited():
    email = queue_email(template_code=PLAIN, to_email="a@b.org")
    OutboxEmail.objects.filter(pk=email.pk).update(status=OutboxStatus.FAILED)
    Job.objects.filter(dedup_key=f"email:{email.pk}").update(status=JobStatus.FAILED, attempts=5)

    run("outbox", retry=email.pk)
    job = Job.objects.get(dedup_key=f"email:{email.pk}")
    assert (job.status, job.attempts) == (JobStatus.PENDING, 0)
    assert AuditLog.objects.filter(action="email.retried", object_id=str(email.pk)).exists()
    run("run_jobs")
    assert len(mail.outbox) == 1


def test_outbox_retry_refuses_sent_or_purged_email():
    email = queue_email(template_code=PLAIN, to_email="a@b.org")
    with pytest.raises(CommandError):
        run("outbox", retry=email.pk)
    with pytest.raises(CommandError):
        run("outbox", retry=999999)
