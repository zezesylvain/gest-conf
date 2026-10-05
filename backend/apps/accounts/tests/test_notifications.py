"""E-mails du compte : contexte en liste blanche et gabarits déclarés (plan L1 §4.2, §8.3)."""

import datetime as dt

import pytest
from django.core import mail
from django.test import RequestFactory

from apps.accounts.adapters import AccountAdapter, request_locale
from apps.accounts.notifications import ALLOWED_CONTEXT_KEYS, safe_context
from apps.accounts.tests.factories import UserFactory
from apps.communications.models import OutboxEmail
from apps.communications.services import fast_path_templates, registered_templates

pytestmark = pytest.mark.django_db


def test_safe_context_keeps_only_whitelisted_strings():
    user = UserFactory()
    context = {
        "user": user,
        "request": RequestFactory().get("/"),
        "current_site": object(),
        "key": "secret",
        "uid": "1",
        "email": user.email,
        "activate_url": "https://conference.test/compte/verifier-email#cle",
        "timestamp": dt.datetime(2026, 10, 5, 14, 30, tzinfo=dt.UTC),
        "ip": None,
    }
    safe = safe_context(context, "fr")
    assert set(safe) == {"activate_url", "timestamp"}
    assert all(isinstance(value, str) for value in safe.values())
    assert safe["timestamp"].endswith("UTC")
    assert set(safe) <= ALLOWED_CONTEXT_KEYS


def test_adapter_queues_instead_of_sending(rf):
    user = UserFactory(locale="en")
    adapter = AccountAdapter(rf.get("/"))
    adapter.send_mail(
        "account/email/password_changed",
        user.email,
        {
            "user": user,
            "ip": "203.0.113.1",
            "user_agent": "UA",
            "timestamp": dt.datetime.now(dt.UTC),
        },
    )
    assert mail.outbox == []
    email = OutboxEmail.objects.get()
    assert (email.to_user, email.locale) == (user, "en")
    assert email.subject == "[GEST-CONF] Your password was changed"
    assert "203.0.113.1" in email.body_text


def test_account_templates_are_registered_with_expected_options():
    templates = {template.code: template for template in registered_templates()}
    sensitive = {code for code, template in templates.items() if template.sensitive}
    assert {
        "account/email/email_confirmation_signup",
        "account/email/email_confirmation",
        "account/email/password_reset_key",
    } <= sensitive
    fast = fast_path_templates()
    # La réinitialisation n'emprunte jamais la voie rapide (oracle temporel, §8.3).
    assert "account/email/password_reset_key" not in fast
    assert {
        "account/email/email_confirmation_signup",
        "account/email/account_already_exists",
        "account/email/email_added",
    } <= fast


@pytest.mark.parametrize(
    ("language", "expected"), [("en-gb", "en"), ("fr", "fr"), ("de", "fr"), (None, "fr")]
)
def test_request_locale(language, expected):
    from django.utils import translation

    with translation.override(language):
        assert request_locale() == expected
