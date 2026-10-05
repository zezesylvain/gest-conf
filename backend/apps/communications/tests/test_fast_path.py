"""Voie rapide (plan L1 §8.3) : liste blanche de gabarits, plafond par requête, repli."""

import pytest
from django.core import mail

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import FAST_PATH_MAX_PER_REQUEST, queue_email
from apps.core.models import Job, JobStatus

from .conftest import FAST

pytestmark = [pytest.mark.django_db, pytest.mark.urls("apps.communications.tests.urls")]


def test_whitelisted_template_is_sent_during_the_request(
    client, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/queue/fast/1")
    assert response.status_code == 200
    assert len(mail.outbox) == 1
    assert OutboxEmail.objects.get().status == OutboxStatus.SENT
    assert Job.objects.get().status == JobStatus.SUCCEEDED


@pytest.mark.parametrize("template", ["plain", "sensitive"])
def test_other_templates_wait_for_the_cron(client, django_capture_on_commit_callbacks, template):
    """Sélection par gabarit : un gabarit sensible hors liste blanche (réinitialisation du
    mot de passe, par exemple) n'est jamais envoyé pendant la requête."""
    with django_capture_on_commit_callbacks(execute=True):
        client.post(f"/queue/{template}/1")
    assert mail.outbox == []
    assert Job.objects.get().status == JobStatus.PENDING


def test_fast_path_capped_per_request(client, django_capture_on_commit_callbacks):
    """Plan §8.3 : 50 e-mails en une requête -> au plus 3 envois immédiats ; les autres
    jobs restent en attente du cron."""
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/queue/fast/50")
    assert len(mail.outbox) == FAST_PATH_MAX_PER_REQUEST == 3
    assert Job.objects.filter(status=JobStatus.PENDING).count() == 47
    # Le budget est propre à chaque requête.
    with django_capture_on_commit_callbacks(execute=True):
        client.post("/queue/fast/2")
    assert len(mail.outbox) == 5


def test_failed_fast_path_falls_back_to_queue(client, settings, django_capture_on_commit_callbacks):
    settings.EMAIL_BACKEND = "apps.communications.tests.test_send.FailingBackend"
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post("/queue/fast/1")
    assert response.status_code == 200
    job = Job.objects.get()
    assert job.status == JobStatus.PENDING
    assert job.attempts == 1
    assert OutboxEmail.objects.get().status == OutboxStatus.QUEUED


def test_no_fast_path_outside_a_request(django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        queue_email(template_code=FAST, to_email="a@b.org", context={"activate_url": "u"})
    assert mail.outbox == []
