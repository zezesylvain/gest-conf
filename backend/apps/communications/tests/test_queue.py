"""Mise en file et rendu des e-mails (plan L1 §8.3, §12.1 « E-mails »)."""

import pytest
from django.core import mail
from django.db import transaction
from django.template import Context
from django.template.loader import get_template
from django.utils import translation

from apps.accounts.tests.factories import UserFactory
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import (
    SEND_EMAIL_JOB,
    fast_path_templates,
    queue_email,
    registered_templates,
)
from apps.core.models import Job, JobPriority, JobStatus

from .conftest import FAST, PLAIN, SENSITIVE

pytestmark = pytest.mark.django_db


def test_queue_email_creates_outbox_row_and_job():
    email = queue_email(
        template_code=PLAIN, to_email="jeanne@univ.ci", context={"display_name": "J"}
    )
    assert email.status == OutboxStatus.QUEUED
    assert email.subject == "[GEST-CONF] Message ordinaire"
    assert "Bonjour J" in email.body_text
    assert email.body_html == ""
    assert email.is_sensitive is False
    job = Job.objects.get(dedup_key=f"email:{email.pk}")
    assert (job.kind, job.payload, job.status) == (
        SEND_EMAIL_JOB,
        {"outbox_id": email.pk},
        "pending",
    )
    assert job.priority == JobPriority.NORMAL
    # Hors requête HTTP : pas de voie rapide, rien n'est envoyé.
    assert mail.outbox == []


def test_sensitive_template_is_flagged_and_prioritised():
    email = queue_email(template_code=SENSITIVE, to_email="a@b.org", context={"activate_url": "u"})
    assert email.is_sensitive is True
    assert Job.objects.get(dedup_key=f"email:{email.pk}").priority == JobPriority.URGENT


def test_html_alternative_is_rendered_when_present():
    email = queue_email(
        template_code=FAST, to_email="a@b.org", context={"activate_url": "https://x"}
    )
    assert '<a href="https://x">' in email.body_html


def test_unknown_template_is_refused():
    with pytest.raises(ValueError):
        queue_email(template_code="tests/email/inconnu", to_email="a@b.org")


@pytest.mark.parametrize("value", [UserFactory, 42, None, ["liste"]])
def test_context_whitelist_only_accepts_strings(value):
    """Plan §8.3 : les gabarits ne reçoivent que des chaînes, jamais d'objet de l'ORM."""
    if value is UserFactory:
        value = UserFactory()
    with pytest.raises(TypeError):
        queue_email(template_code=PLAIN, to_email="a@b.org", context={"user": value})
    assert not OutboxEmail.objects.exists()


@pytest.mark.parametrize("key", ["site_name", "Majuscule", "avec-tiret"])
def test_context_reserved_or_malformed_keys_are_refused(key):
    with pytest.raises(ValueError):
        queue_email(template_code=PLAIN, to_email="a@b.org", context={key: "x"})


def test_idempotency_key_returns_existing_email():
    first = queue_email(template_code=PLAIN, to_email="a@b.org", idempotency_key="tests:1")
    second = queue_email(template_code=PLAIN, to_email="a@b.org", idempotency_key="tests:1")
    assert first.pk == second.pk
    assert OutboxEmail.objects.count() == 1


def test_nothing_queued_when_transaction_is_rolled_back():
    """Schéma « transactional outbox » : une action annulée n'envoie aucun e-mail."""
    with pytest.raises(RuntimeError), transaction.atomic():
        queue_email(template_code=FAST, to_email="a@b.org", context={"activate_url": "u"})
        raise RuntimeError("échec du service")
    assert not OutboxEmail.objects.exists()
    assert not Job.objects.exists()
    assert mail.outbox == []


# --- Langue du destinataire -------------------------------------------------------------


def test_rendered_in_user_locale_rather_than_request_locale():
    user = UserFactory(locale="en")
    with translation.override("fr"):
        email = queue_email(
            template_code="communications/email/test", to_email=user.email, to_user=user
        )
    assert email.locale == "en"
    assert email.subject == "[GEST-CONF] Test email"
    assert "This test message" in email.body_text


def test_explicit_locale_wins_over_user_locale():
    user = UserFactory(locale="en")
    email = queue_email(
        template_code="communications/email/test", to_email=user.email, to_user=user, locale="fr"
    )
    assert email.locale == "fr"
    assert email.subject == "[GEST-CONF] E-mail de test"


def test_request_locale_used_without_account():
    with translation.override("en-gb"):
        email = queue_email(template_code="communications/email/test", to_email="x@y.org")
    assert email.locale == "en"


def test_unsupported_locale_falls_back_to_default():
    email = queue_email(template_code="communications/email/test", to_email="x@y.org", locale="de")
    assert email.locale == "fr"


# --- Gabarits : registre et objets sans donnée personnelle ----------------------------------

SENTINEL = "SENTINELLE-PERSONNELLE"


class _SentinelContext(dict):
    """Toute variable vaut la sentinelle, sauf le nom du site (fixe, non personnel)."""

    def __contains__(self, key):
        return True

    def __getitem__(self, key):
        return "GEST-CONF" if key == "site_name" else SENTINEL


def subject_leaks_variables(code: str) -> bool:
    template = get_template(f"{code}_subject.txt").template
    with translation.override("fr"):
        french = template.render(Context(_SentinelContext()))
    with translation.override("en"):
        english = template.render(Context(_SentinelContext()))
    return SENTINEL in french or SENTINEL in english


def test_subject_detector_catches_personal_variables():
    assert subject_leaks_variables("tests/email/leaky") is True


def test_subject_templates_have_no_personal_data():
    """Plan §8.3 : l'objet est conservé après la purge des corps (D15) ; aucun gabarit
    d'objet n'affiche de variable autre que le nom du site."""
    leaking = [t.code for t in registered_templates() if subject_leaks_variables(t.code)]
    assert leaking == []


def test_fast_path_is_a_whitelist_of_templates():
    """Plan §8.3 : sélection par gabarit, pas par priorité ; l'e-mail de test n'y est pas."""
    assert FAST in fast_path_templates()
    assert "communications/email/test" not in fast_path_templates()
    assert SENSITIVE not in fast_path_templates()


def test_queued_job_status_is_pending():
    email = queue_email(template_code=PLAIN, to_email="a@b.org")
    assert Job.objects.get(dedup_key=f"email:{email.pk}").status == JobStatus.PENDING
