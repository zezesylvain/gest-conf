"""Commandes d'opérateur des e-mails (plan L1 §9.4) : send_test_email, outbox."""

import io

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.core.audit import AuditAction, contains_clear_email
from apps.core.jobs import process_jobs
from apps.core.models import AuditLog, Job, JobStatus

pytestmark = pytest.mark.django_db


def run(name, *args):
    out = io.StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def system_user(monkeypatch):
    monkeypatch.setattr("getpass.getuser", lambda: "exploitant")


# --- send_test_email -----------------------------------------------------------------------


def test_send_test_email_queues_for_the_cron_and_is_audited(system_user):
    output = run("send_test_email", "--to", "Operateur@Exemple.org", "--reason", "jalon J-tech")
    email = OutboxEmail.objects.get()
    assert email.template_code == "communications.test_email"
    assert email.to_email == "Operateur@Exemple.org"
    assert email.locale == "fr"
    assert mail.outbox == []  # le cron l'envoie (critère J-tech)
    assert "O***@Exemple.org" in output and "Operateur@" not in output
    entry = AuditLog.objects.get()
    assert entry.action == AuditAction.COMMAND_SEND_TEST_EMAIL
    assert (entry.actor_kind, entry.actor_label, entry.actor) == ("command", "cli:exploitant", None)
    assert (entry.object_type, entry.object_id) == ("communications.outboxemail", str(email.pk))
    assert entry.after == {"to_masked": "O***@Exemple.org", "locale": "fr"}
    assert entry.reason == "jalon J-tech"
    assert process_jobs(max_seconds=10, worker="cron:1") == 1
    assert mail.outbox[0].to == ["Operateur@Exemple.org"]


def test_send_test_email_in_english():
    run("send_test_email", "--to", "ops@example.org", "--locale", "en")
    email = OutboxEmail.objects.get()
    assert email.locale == "en"
    assert email.subject == "[GEST-CONF] Test email"


def test_send_test_email_rejects_invalid_address():
    with pytest.raises(CommandError):
        run("send_test_email", "--to", "pas-une-adresse")
    assert not OutboxEmail.objects.exists()
    assert not AuditLog.objects.exists()


def test_send_test_email_rejects_unknown_locale():
    with pytest.raises(CommandError):
        run("send_test_email", "--to", "ops@example.org", "--locale", "de")


# --- outbox ----------------------------------------------------------------------------------


def _failed_email():
    run("send_test_email", "--to", "jean.dupont@univ.ci")
    email = OutboxEmail.objects.get()
    OutboxEmail.objects.filter(pk=email.pk).update(
        status=OutboxStatus.FAILED, attempts=5, last_error="SMTPException: refus\nsuite"
    )
    Job.objects.filter(dedup_key=f"email:{email.pk}").update(
        status=JobStatus.FAILED, attempts=5, finished_at=email.created_at
    )
    AuditLog.objects.all()._privileged_delete()
    return email


def test_outbox_lists_with_masked_addresses():
    email = _failed_email()
    output = run("outbox", "--status", "failed")
    assert f"#{email.pk}" in output
    assert "j***@univ.ci" in output
    assert "jean.dupont" not in output
    assert "SMTPException: refus" in output and "suite" not in output
    assert run("outbox", "--status", "sent").strip() == "Aucun e-mail."
    assert not AuditLog.objects.exists()  # la consultation n'est pas auditée


def test_rg17_command_requires_reason():
    """RG-17 : une commande sensible exige un motif, refusé avant toute modification."""
    email = _failed_email()
    for args in (["--retry", str(email.pk)], ["--retry", str(email.pk), "--reason", "   "]):
        with pytest.raises(CommandError, match="Motif obligatoire"):
            run("outbox", *args)
    email.refresh_from_db()
    assert email.status == OutboxStatus.FAILED
    assert not AuditLog.objects.exists()


def test_outbox_retry_requeues_and_is_audited(system_user):
    email = _failed_email()
    output = run("outbox", "--retry", str(email.pk), "--reason", "boîte du destinataire rétablie")
    assert "remis en file" in output
    email.refresh_from_db()
    assert email.status == OutboxStatus.QUEUED
    job = Job.objects.get(dedup_key=f"email:{email.pk}")
    assert (job.status, job.attempts, job.finished_at) == (JobStatus.PENDING, 0, None)
    entry = AuditLog.objects.get()
    assert entry.action == AuditAction.COMMAND_OUTBOX_RETRY
    assert entry.reason == "boîte du destinataire rétablie"
    assert entry.actor_label == "cli:exploitant"
    assert entry.before["status"] == "failed" and entry.after["status"] == "queued"
    assert entry.after["to_email_masked"] == "j***@univ.ci"
    assert not contains_clear_email([entry.before, entry.after])
    assert process_jobs(max_seconds=10, worker="cron:1") == 1
    email.refresh_from_db()
    assert email.status == OutboxStatus.SENT


def test_outbox_retry_recreates_a_purged_job():
    """Tâche terminée supprimée (30 jours) : une nouvelle tâche est créée."""
    email = _failed_email()
    Job.objects.all().delete()
    run("outbox", "--retry", str(email.pk), "--reason", "relance")
    assert Job.objects.get(dedup_key=f"email:{email.pk}").status == JobStatus.PENDING


@pytest.mark.parametrize("status", [OutboxStatus.SENT, OutboxStatus.QUEUED])
def test_outbox_retry_refuses_non_failed_emails(status):
    email = _failed_email()
    OutboxEmail.objects.filter(pk=email.pk).update(status=status)
    with pytest.raises(CommandError, match="en échec"):
        run("outbox", "--retry", str(email.pk), "--reason", "x")
    assert not AuditLog.objects.exists()


def test_outbox_retry_refuses_purged_body():
    from django.utils import timezone

    email = _failed_email()
    OutboxEmail.objects.filter(pk=email.pk).update(purged_at=timezone.now(), body_text="")
    with pytest.raises(CommandError, match="purgé"):
        run("outbox", "--retry", str(email.pk), "--reason", "x")


def test_outbox_retry_unknown_id():
    with pytest.raises(CommandError, match="introuvable"):
        run("outbox", "--retry", "999", "--reason", "x")
