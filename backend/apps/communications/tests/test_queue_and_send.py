"""E-mails (plan L1 §8.3, §4.7) : mise en file, rendu dans la langue, envoi, plafond horaire."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import override_settings
from django.utils import timezone, translation

from apps.accounts.tests.factories import UserFactory
from apps.communications import services
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import (
    SEND_EMAIL_JOB,
    TEST_EMAIL,
    hourly_cap_release,
    message_id,
    queue_email,
    resolve_locale,
)
from apps.core.jobs import JobOutcome, process_jobs, run_job
from apps.core.models import Job, JobStatus

pytestmark = pytest.mark.django_db

CODE = TEST_EMAIL.code
CONTEXT = {"timestamp": "5 octobre 2026 12:00 UTC"}


def queue(**kwargs):
    params = {"to_email": "destinataire@example.org", "context": CONTEXT, **kwargs}
    return queue_email(CODE, **params)


def job_of(email):
    return Job.objects.get(dedup_key=f"email:{email.pk}")


# --- Mise en file ----------------------------------------------------------------------------


def test_queue_email_renders_and_creates_outbox_and_job():
    email = queue(locale="fr")
    assert email.status == OutboxStatus.QUEUED
    assert email.subject == "[GEST-CONF] E-mail de test"
    assert "5 octobre 2026 12:00 UTC" in email.body_text
    assert "<html" in email.body_html and 'lang="fr"' in email.body_html
    assert email.locale == "fr"
    assert not email.is_sensitive
    job = job_of(email)
    assert job.kind == SEND_EMAIL_JOB
    assert job.payload == {"outbox_id": email.pk}
    assert job.priority == 100  # hors voie rapide
    assert mail.outbox == []  # rien n'est envoyé pendant la mise en file


def test_queue_email_renders_in_english():
    email = queue(locale="en")
    assert email.locale == "en"
    assert email.subject == "[GEST-CONF] Test email"
    assert "This is a test email" in email.body_text
    assert 'lang="en"' in email.body_html


def test_text_body_is_not_html_escaped_but_html_body_is():
    email = queue(context={"timestamp": "<b>&</b>"})
    assert "<b>&</b>" in email.body_text
    assert "&lt;b&gt;&amp;&lt;/b&gt;" in email.body_html


@pytest.mark.parametrize(
    ("explicit", "user_locale", "request_language", "expected"),
    [
        ("en", "fr", "fr", "en"),
        (None, "en", "fr", "en"),
        (None, None, "en", "en"),
        (None, None, "de", "fr"),
        ("en-us", None, "fr", "en"),
    ],
)
def test_locale_resolution(explicit, user_locale, request_language, expected):
    """Langue du destinataire : explicite, sinon celle du compte, sinon celle de la requête."""
    user = UserFactory(locale=user_locale) if user_locale else None
    with translation.override(request_language):
        assert resolve_locale(explicit, user) == expected


def test_user_locale_is_used_for_rendering():
    user = UserFactory(locale="en")
    with translation.override("fr"):
        email = queue(to_user=user)
    assert email.locale == "en"
    assert email.to_user == user
    assert email.subject == "[GEST-CONF] Test email"


def test_unknown_template_is_refused():
    with pytest.raises(ValueError, match="inconnu"):
        queue_email("account.nothing", to_email="a@example.org")


def test_invalid_address_is_refused():
    with pytest.raises(ValidationError):
        queue(to_email="pas-une-adresse")
    assert not OutboxEmail.objects.exists()


def test_context_whitelist_refuses_undeclared_keys():
    """Contexte en liste blanche (§8.3) : une clé non déclarée par le gabarit est refusée."""
    with pytest.raises(ValueError, match="non déclarées"):
        queue(context={"timestamp": "x", "user": "objet"})


@pytest.mark.parametrize("value", [object(), 42, None, ["liste"]])
def test_context_values_must_be_strings(value):
    """Les gabarits du projet ne reçoivent que des chaînes (jamais un objet de l'ORM)."""
    with pytest.raises(TypeError, match="chaînes"):
        queue(context={"timestamp": value})


def test_template_registration_refuses_keys_outside_the_whitelist():
    from django.core.exceptions import ImproperlyConfigured

    with pytest.raises(ImproperlyConfigured, match="liste blanche"):
        services.register_template(
            services.EmailTemplate(code="tests.bad", prefix="x", context_keys=frozenset({"user"}))
        )


def test_queue_email_is_part_of_the_caller_transaction():
    """Une action annulée n'envoie aucun e-mail : ni OutboxEmail ni Job."""
    with pytest.raises(RuntimeError), transaction.atomic():
        queue()
        raise RuntimeError
    assert not OutboxEmail.objects.exists()
    assert not Job.objects.exists()


def test_idempotency_key_returns_the_existing_email():
    first = queue(idempotency_key="test:1")
    second = queue(idempotency_key="test:1")
    assert first.pk == second.pk
    assert OutboxEmail.objects.count() == 1
    assert Job.objects.count() == 1


def test_scheduled_email_waits(settings):
    later = timezone.now() + timedelta(hours=1)
    email = queue(scheduled_at=later)
    assert job_of(email).run_at == later
    assert process_jobs(max_seconds=10, worker="w:1") == 0


def test_subject_is_single_line_and_bounded(monkeypatch):
    monkeypatch.setattr(
        services, "render_to_string", lambda name, context: "Objet\nsur deux lignes " + "x" * 400
    )
    email = queue()
    assert "\n" not in email.subject
    assert len(email.subject) == 255


# --- Envoi par la file (cron) ------------------------------------------------------------------


def test_send_marks_sent_with_message_id():
    email = queue(locale="fr")
    assert process_jobs(max_seconds=10, worker="w:1") == 1
    email.refresh_from_db()
    assert email.status == OutboxStatus.SENT
    assert email.sent_at is not None
    assert email.attempts == 1
    assert email.body_text  # non sensible : corps conservé (30 jours, D15)
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    assert sent.to == ["destinataire@example.org"]
    assert sent.subject == email.subject
    assert sent.from_email == "GEST-CONF <no-reply@conference.exemple.org>"
    assert sent.extra_headers["Message-ID"] == message_id(email)
    assert message_id(email).startswith(f"<gestconf.{email.pk}.")
    assert message_id(email).endswith("@conference.exemple.org>")
    assert sent.alternatives[0].mimetype == "text/html"
    assert job_of(email).status == JobStatus.SUCCEEDED


def test_send_is_idempotent_by_double_execution():
    """Un e-mail déjà envoyé n'est jamais renvoyé, même si sa tâche est rejouée."""
    email = queue()
    job = job_of(email)
    assert run_job(job.pk, worker="w:1") == JobOutcome.SUCCEEDED
    Job.objects.filter(pk=job.pk).update(status=JobStatus.PENDING)  # rejeu forcé
    assert run_job(job.pk, worker="w:2") == JobOutcome.SUCCEEDED
    assert len(mail.outbox) == 1
    email.refresh_from_db()
    assert email.attempts == 1


def test_sensitive_body_is_purged_after_sending(monkeypatch):
    sensitive = services.EmailTemplate(
        code="tests.sensitive",
        prefix=TEST_EMAIL.prefix,
        context_keys=TEST_EMAIL.context_keys,
        is_sensitive=True,
    )
    monkeypatch.setitem(services.EMAIL_TEMPLATES, sensitive.code, sensitive)
    email = queue_email(sensitive.code, to_email="a@example.org", context=CONTEXT)
    assert email.is_sensitive and email.body_text
    process_jobs(max_seconds=10, worker="w:1")
    email.refresh_from_db()
    assert email.status == OutboxStatus.SENT
    assert (email.body_text, email.body_html) == ("", "")
    assert email.purged_at == email.sent_at
    assert email.subject  # l'objet reste (métadonnées d'envoi)
    assert "test" in mail.outbox[0].body.lower()  # parti avant la purge


@override_settings(EMAIL_BACKEND="apps.communications.backends.UnconfiguredEmailBackend")
def test_failure_requeues_then_marks_failed():
    email = queue()
    job = job_of(email)
    Job.objects.filter(pk=job.pk).update(max_attempts=2)
    assert run_job(job.pk, worker="w:1") == JobOutcome.RETRY
    email.refresh_from_db()
    assert email.status == OutboxStatus.QUEUED
    assert email.attempts == 1
    assert "ImproperlyConfigured" in email.last_error
    Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
    assert run_job(job.pk, worker="w:1") == JobOutcome.FAILED
    email.refresh_from_db()
    assert email.status == OutboxStatus.FAILED
    assert email.attempts == 2


def test_status_is_committed_as_sending_before_calling_the_provider(monkeypatch):
    """« sending » validé avant l'appel au fournisseur (§8.3) : visible depuis le backend."""
    seen = []

    from django.core.mail.backends.locmem import EmailBackend

    original = EmailBackend.send_messages

    def spy(self, messages):
        seen.append(OutboxEmail.objects.get().status)
        return original(self, messages)

    monkeypatch.setattr(EmailBackend, "send_messages", spy)
    queue()
    process_jobs(max_seconds=10, worker="w:1")
    assert seen == [OutboxStatus.SENDING]


def test_cancelled_or_missing_email_is_skipped():
    email = queue()
    OutboxEmail.objects.filter(pk=email.pk).update(status=OutboxStatus.CANCELLED)
    assert run_job(job_of(email).pk, worker="w:1") == JobOutcome.SUCCEEDED
    other = queue()
    job = job_of(other)
    OutboxEmail.objects.filter(pk=other.pk).delete()
    assert run_job(job.pk, worker="w:1") == JobOutcome.SUCCEEDED
    assert mail.outbox == []


def test_purged_unsent_email_is_cancelled_instead_of_sent():
    email = queue()
    OutboxEmail.objects.filter(pk=email.pk).update(
        body_text="", body_html="", purged_at=timezone.now()
    )
    run_job(job_of(email).pk, worker="w:1")
    email.refresh_from_db()
    assert email.status == OutboxStatus.CANCELLED
    assert mail.outbox == []


# --- Plafond global d'envoi par heure (§4.7) ---------------------------------------------------


def _sent_recently(count, minutes_ago=10):
    now = timezone.now()
    for index in range(count):
        OutboxEmail.objects.create(
            to_email=f"x{index}@example.org",
            template_code=CODE,
            locale="fr",
            subject="s",
            status=OutboxStatus.SENT,
            sent_at=now - timedelta(minutes=minutes_ago, seconds=index),
        )


def test_hourly_cap_defers_to_the_queue(settings):
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 3
    _sent_recently(3)
    email = queue()
    job = job_of(email)
    assert run_job(job.pk, worker="w:1") == JobOutcome.DEFERRED
    job.refresh_from_db()
    email.refresh_from_db()
    assert (job.status, job.attempts) == (JobStatus.PENDING, 0)  # aucune tentative consommée
    assert email.status == OutboxStatus.QUEUED
    # Libéré quand le plus ancien des envois récents sort de la fenêtre d'une heure.
    assert (
        timezone.now() + timedelta(minutes=49) < job.run_at < timezone.now() + timedelta(minutes=51)
    )
    assert email.scheduled_at == job.run_at
    assert mail.outbox == []


def test_hourly_cap_counts_only_the_last_hour(settings):
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 3
    _sent_recently(3, minutes_ago=61)
    assert hourly_cap_release(timezone.now()) is None
    queue()
    assert process_jobs(max_seconds=10, worker="w:1") == 1
    assert len(mail.outbox) == 1


def test_hourly_cap_release_accounts_for_overshoot(settings):
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 2
    _sent_recently(4)  # dépassement (envoyeurs simultanés) : 3 doivent sortir de la fenêtre
    now = timezone.now()
    release = hourly_cap_release(now)
    third_oldest = sorted(OutboxEmail.objects.values_list("sent_at", flat=True))[2]
    assert release == third_oldest + timedelta(hours=1, seconds=1)
