"""Conservation du registre d'envoi (D15, plan L1 §3.6, §8.4)."""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.retention import purge_sensitive_bodies
from apps.core.actor import Actor
from apps.core.models import CronHeartbeat, Job, JobStatus

pytestmark = pytest.mark.django_db

SYSTEM = Actor.system("job:test")


def make_email(*, sensitive, status, age, with_job=False):
    email = OutboxEmail.objects.create(
        to_email="a@example.org",
        template_code="tests.x",
        locale="fr",
        subject="Objet",
        body_text="Lien : https://exemple.org/verifier/CLE-SECRETE",
        body_html="<p>CLE-SECRETE</p>",
        is_sensitive=sensitive,
        status=status,
    )
    OutboxEmail.objects.filter(pk=email.pk).update(created_at=timezone.now() - age)
    if with_job:
        Job.objects.create(
            kind="communications.send_email",
            payload={"outbox_id": email.pk},
            dedup_key=f"email:{email.pk}",
        )
    email.refresh_from_db()
    return email


def test_sensitive_bodies_purged_after_24h_and_email_cancelled():
    """Sécurité (§3.6) : un lien à jeton ne reste jamais plus de 24 h en base."""
    old_failed = make_email(
        sensitive=True, status=OutboxStatus.FAILED, age=timedelta(hours=25), with_job=True
    )
    old_queued = make_email(
        sensitive=True, status=OutboxStatus.QUEUED, age=timedelta(hours=25), with_job=True
    )
    recent = make_email(sensitive=True, status=OutboxStatus.FAILED, age=timedelta(hours=2))
    sent_not_purged = make_email(sensitive=True, status=OutboxStatus.SENT, age=timedelta(0))
    not_sensitive = make_email(sensitive=False, status=OutboxStatus.FAILED, age=timedelta(days=2))
    now = timezone.now()
    assert purge_sensitive_bodies(now, SYSTEM) == 3
    for email in (old_failed, old_queued, sent_not_purged):
        email.refresh_from_db()
        assert (email.body_text, email.body_html, email.purged_at) == ("", "", now)
    old_failed.refresh_from_db()
    old_queued.refresh_from_db()
    assert old_failed.status == old_queued.status == OutboxStatus.CANCELLED
    assert set(Job.objects.values_list("status", flat=True)) == {JobStatus.CANCELLED}
    sent_not_purged.refresh_from_db()
    assert sent_not_purged.status == OutboxStatus.SENT
    for email in (recent, not_sensitive):
        email.refresh_from_db()
        assert "CLE-SECRETE" in email.body_text
    assert purge_sensitive_bodies(timezone.now(), SYSTEM) == 0  # idempotente


def test_sensitive_purge_runs_with_each_run_jobs_pass():
    email = make_email(sensitive=True, status=OutboxStatus.FAILED, age=timedelta(hours=30))
    call_command("run_jobs")
    email.refresh_from_db()
    assert email.body_text == ""
    purges = CronHeartbeat.objects.get(name="run_jobs").summary["purges"]
    assert purges["communications.sensitive_bodies"]["count"] == 1
    assert "communications.email_bodies" not in purges  # le cadre légal attend cleanup


def test_legal_email_purges_are_simulated_by_default(settings):
    settings.GESTCONF_RETENTION_ENFORCE = False
    body = make_email(sensitive=False, status=OutboxStatus.SENT, age=timedelta(days=31))
    meta = make_email(sensitive=False, status=OutboxStatus.SENT, age=timedelta(days=400))
    call_command("cleanup")
    assert OutboxEmail.objects.filter(pk=meta.pk).exists()
    body.refresh_from_db()
    assert body.body_text
    rules = CronHeartbeat.objects.get(name="cleanup").summary["rules"]
    assert rules["communications.email_bodies"] == {
        "category": "legal",
        "mode": "simulated",
        "count": 2,
    }
    assert rules["communications.email_metadata"]["count"] == 1


def test_legal_email_purges_when_enforced(settings):
    settings.GESTCONF_RETENTION_ENFORCE = True
    body = make_email(sensitive=False, status=OutboxStatus.SENT, age=timedelta(days=31))
    meta = make_email(sensitive=False, status=OutboxStatus.SENT, age=timedelta(days=400))
    queued = make_email(sensitive=False, status=OutboxStatus.QUEUED, age=timedelta(days=400))
    call_command("cleanup")
    assert not OutboxEmail.objects.filter(pk=meta.pk).exists()
    body.refresh_from_db()
    assert (body.body_text, body.body_html) == ("", "")
    assert body.subject == "Objet"  # métadonnées conservées 12 mois
    queued.refresh_from_db()
    assert queued.body_text  # jamais un e-mail encore à envoyer
