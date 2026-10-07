"""Voie rapide d'envoi (plan L1 §8.3) : liste blanche de gabarits, plafond par requête,
même réservation que le cron, jamais pour la réinitialisation du mot de passe."""

import pytest
from django.core import mail
from django.db import transaction
from django.http import JsonResponse
from django.test import Client, override_settings
from django.urls import path

from apps.communications import services
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import (
    FAST_PATH_TEMPLATES,
    NEVER_FAST_PATH_TEMPLATES,
    TEST_EMAIL,
    queue_email,
)
from apps.core.jobs import process_jobs
from apps.core.models import Job, JobStatus
from apps.core.request_context import (
    FAST_PATH_MAX_PER_REQUEST,
    fast_path_remaining,
    request_scope,
)

CONTEXT = {"timestamp": "maintenant"}


def queue_many_view(request, count):
    """Comme une création d'invitations en masse : N e-mails dans une même transaction."""
    with transaction.atomic():
        for index in range(count):
            queue_email(TEST_EMAIL.code, to_email=f"invite{index}@example.org", context=CONTEXT)
        sent_during_transaction = len(mail.outbox)
    return JsonResponse(
        {"during_transaction": sent_during_transaction, "after_commit": len(mail.outbox)}
    )


urlpatterns = [path("queue/<int:count>", queue_many_view)]


@pytest.fixture
def fast_test_email(monkeypatch):
    """Le seul gabarit réel de L1.2 (e-mail de test) placé, pour le test, en voie rapide."""
    monkeypatch.setattr(services, "FAST_PATH_TEMPLATES", frozenset({TEST_EMAIL.code}))


def test_password_reset_never_takes_the_fast_path():
    """Oracle temporel (§8.3, R20) : la réinitialisation attend toujours le cron."""
    assert "account.password_reset_key" in NEVER_FAST_PATH_TEMPLATES
    assert not FAST_PATH_TEMPLATES & NEVER_FAST_PATH_TEMPLATES
    assert not any("password_reset" in code for code in FAST_PATH_TEMPLATES)


def test_fast_path_whitelist_matches_the_plan():
    """Inscription, compte existant, invitations, liaison d'adresse (RG-20), notifications
    de sécurité dont « adresse ajoutée » (§8.3) ; l'e-mail de test n'en fait pas partie."""
    assert {
        "account.email_confirmation_signup",
        "account.account_already_exists",
        "role.invitation",
        "role.invitation_link",
        "account.email_added",
    } <= FAST_PATH_TEMPLATES
    assert TEST_EMAIL.code not in FAST_PATH_TEMPLATES


@pytest.mark.django_db(transaction=True)
@pytest.mark.urls(__name__)
def test_fast_path_capped_per_request(fast_test_email):
    """§8.3 v3 : 50 e-mails dans une requête → au plus 3 envois pendant la requête, après
    la validation de la transaction ; les autres tâches restent en attente pour le cron."""
    response = Client().get("/queue/50")
    assert response.json() == {"during_transaction": 0, "after_commit": FAST_PATH_MAX_PER_REQUEST}
    assert len(mail.outbox) == 3
    assert OutboxEmail.objects.filter(status=OutboxStatus.SENT).count() == 3
    assert Job.objects.filter(status=JobStatus.PENDING).count() == 47
    assert set(Job.objects.values_list("priority", flat=True)) == {0}
    # Le compteur est propre à la requête : la suivante a de nouveau droit à 3 envois.
    assert Client().get("/queue/5").json()["after_commit"] == 6
    # Le cron envoie le reste, sans doublon.
    assert process_jobs(max_seconds=60, worker="cron:1") == 49
    assert len(mail.outbox) == 55
    # Chaque e-mail est parti une seule fois (un Message-ID par ligne OutboxEmail).
    assert len({message.extra_headers["Message-ID"] for message in mail.outbox}) == 55


@pytest.mark.django_db(transaction=True)
@pytest.mark.urls(__name__)
def test_fast_path_is_selected_by_template_not_priority():
    """Gabarit hors liste blanche : aucun envoi pendant la requête, même un seul."""
    response = Client().get("/queue/1")
    assert response.json()["after_commit"] == 0
    assert Job.objects.get().priority == 100


@pytest.mark.django_db(transaction=True)
def test_no_fast_path_outside_a_request(fast_test_email):
    """Hors requête (cron, commande) : pas de budget, le cron envoie."""
    assert fast_path_remaining() is None
    queue_email(TEST_EMAIL.code, to_email="a@example.org", context=CONTEXT)
    assert mail.outbox == []


@pytest.mark.django_db(transaction=True)
def test_fast_path_runs_only_after_commit_and_not_on_rollback(fast_test_email):
    with request_scope():
        with pytest.raises(RuntimeError), transaction.atomic():
            queue_email(TEST_EMAIL.code, to_email="a@example.org", context=CONTEXT)
            raise RuntimeError
        assert mail.outbox == []
        assert not Job.objects.exists()
        with transaction.atomic():
            queue_email(TEST_EMAIL.code, to_email="b@example.org", context=CONTEXT)
            assert mail.outbox == []
        assert [message.to for message in mail.outbox] == [["b@example.org"]]


@pytest.mark.django_db(transaction=True)
@override_settings(EMAIL_BACKEND="apps.communications.backends.UnconfiguredEmailBackend")
def test_fast_path_failure_leaves_the_job_to_the_cron(fast_test_email, settings):
    """Échec de l'envoi immédiat : la requête aboutit, la tâche est reprise par le cron."""
    with request_scope():
        email = queue_email(TEST_EMAIL.code, to_email="a@example.org", context=CONTEXT)
    job = Job.objects.get()
    assert (job.status, job.attempts) == (JobStatus.PENDING, 1)
    email.refresh_from_db()
    assert email.status == OutboxStatus.QUEUED
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    Job.objects.update(run_at=job.created_at)
    assert process_jobs(max_seconds=10, worker="cron:1") == 1
    assert len(mail.outbox) == 1


@pytest.mark.django_db(transaction=True)
def test_fast_path_uses_the_short_network_timeout(fast_test_email, settings, monkeypatch):
    seen = {}
    original = services.get_connection

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return original(*args, **kwargs)

    settings.GESTCONF_EMAIL_FAST_PATH_TIMEOUT = 2.5
    monkeypatch.setattr(services, "get_connection", spy)
    with request_scope():
        queue_email(TEST_EMAIL.code, to_email="a@example.org", context=CONTEXT)
    assert seen == {"timeout": 2.5}


@pytest.mark.django_db(transaction=True)
def test_fast_path_and_cron_never_send_the_same_email_twice(fast_test_email):
    """Même réservation conditionnelle : le cron qui passe après la voie rapide n'envoie rien."""
    with request_scope():
        queue_email(TEST_EMAIL.code, to_email="a@example.org", context=CONTEXT)
    assert process_jobs(max_seconds=10, worker="cron:1") == 0
    assert len(mail.outbox) == 1


def test_request_scope_resets_the_budget():
    assert fast_path_remaining() is None
    with request_scope():
        assert fast_path_remaining() == FAST_PATH_MAX_PER_REQUEST
        with request_scope(fast_path_limit=1):
            assert fast_path_remaining() == 1
        assert fast_path_remaining() == FAST_PATH_MAX_PER_REQUEST
    assert fast_path_remaining() is None
