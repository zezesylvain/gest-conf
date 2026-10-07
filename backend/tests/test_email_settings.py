"""Backends d'e-mail par environnement (D10, plan L1 §8.3) et garde de démarrage en production."""

import subprocess
import sys

import environ
import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils.module_loading import import_string

from apps.communications.backends import UnconfiguredEmailBackend, require_email_provider
from config.settings.base import ANYMAIL_BACKENDS, email_settings_from_env

SECRET = "valeur-tres-secrete-0123456789"


def from_env(monkeypatch, **variables):
    for name in (
        "GESTCONF_EMAIL_PROVIDER",
        "DEFAULT_FROM_EMAIL",
        "GESTCONF_BREVO_API_KEY",
        "GESTCONF_MAILJET_API_KEY",
        "GESTCONF_MAILJET_SECRET_KEY",
        "GESTCONF_SMTP_HOST",
        "GESTCONF_SMTP_PORT",
        "GESTCONF_SMTP_USER",
        "GESTCONF_SMTP_PASSWORD",
        "GESTCONF_SMTP_USE_SSL",
    ):
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    return email_settings_from_env(environ.Env(), timeout=7)


def test_test_settings_use_locmem():
    assert settings.EMAIL_BACKEND == "django.core.mail.backends.locmem.EmailBackend"


def test_anymail_backend_classes_exist():
    """Classes vérifiées dans anymail 15.2 (D10, « à vérifier » du plan levé)."""
    for path in ANYMAIL_BACKENDS.values():
        assert import_string(path).__name__ == "EmailBackend"


def test_no_provider_means_explicit_failure_on_send(monkeypatch):
    result = from_env(monkeypatch)
    assert result == {
        "GESTCONF_EMAIL_PROVIDER": "",
        "EMAIL_BACKEND": "apps.communications.backends.UnconfiguredEmailBackend",
    }
    with pytest.raises(ImproperlyConfigured, match="GESTCONF_EMAIL_PROVIDER"):
        UnconfiguredEmailBackend().send_messages([])


def test_brevo(monkeypatch):
    result = from_env(
        monkeypatch,
        GESTCONF_EMAIL_PROVIDER="Brevo",
        DEFAULT_FROM_EMAIL="Conférence <no-reply@conference.exemple.org>",
        GESTCONF_BREVO_API_KEY=SECRET,
    )
    assert result["EMAIL_BACKEND"] == "anymail.backends.brevo.EmailBackend"
    assert result["ANYMAIL"] == {"BREVO_API_KEY": SECRET, "REQUESTS_TIMEOUT": 7}
    assert result["DEFAULT_FROM_EMAIL"] == result["SERVER_EMAIL"]


def test_mailjet(monkeypatch):
    result = from_env(
        monkeypatch,
        GESTCONF_EMAIL_PROVIDER="mailjet",
        DEFAULT_FROM_EMAIL="no-reply@conference.exemple.org",
        GESTCONF_MAILJET_API_KEY="cle",
        GESTCONF_MAILJET_SECRET_KEY=SECRET,
    )
    assert result["EMAIL_BACKEND"] == "anymail.backends.mailjet.EmailBackend"
    assert result["ANYMAIL"]["MAILJET_SECRET_KEY"] == SECRET
    assert result["ANYMAIL"]["REQUESTS_TIMEOUT"] == 7


def test_smtp_fallback(monkeypatch):
    result = from_env(
        monkeypatch,
        GESTCONF_EMAIL_PROVIDER="smtp",
        DEFAULT_FROM_EMAIL="no-reply@conference.exemple.org",
        GESTCONF_SMTP_HOST="mail.exemple.org",
        GESTCONF_SMTP_USER="compte",
        GESTCONF_SMTP_PASSWORD=SECRET,
        GESTCONF_SMTP_USE_SSL="true",
    )
    assert result["EMAIL_BACKEND"] == "django.core.mail.backends.smtp.EmailBackend"
    assert (result["EMAIL_HOST"], result["EMAIL_PORT"]) == ("mail.exemple.org", 465)
    assert (result["EMAIL_USE_SSL"], result["EMAIL_USE_TLS"]) == (True, False)
    assert result["EMAIL_TIMEOUT"] == 7


@pytest.mark.parametrize(
    ("variables", "missing"),
    [
        ({"GESTCONF_EMAIL_PROVIDER": "brevo"}, "DEFAULT_FROM_EMAIL, GESTCONF_BREVO_API_KEY"),
        (
            {
                "GESTCONF_EMAIL_PROVIDER": "mailjet",
                "DEFAULT_FROM_EMAIL": "a@b.org",
                "GESTCONF_MAILJET_API_KEY": SECRET,
            },
            "GESTCONF_MAILJET_SECRET_KEY",
        ),
        (
            {
                "GESTCONF_EMAIL_PROVIDER": "smtp",
                "DEFAULT_FROM_EMAIL": "a@b.org",
                "GESTCONF_SMTP_USER": "compte",
            },
            "GESTCONF_SMTP_HOST, GESTCONF_SMTP_PASSWORD",
        ),
    ],
)
def test_incomplete_provider_fails_without_leaking_values(monkeypatch, variables, missing):
    with pytest.raises(ImproperlyConfigured) as error:
        from_env(monkeypatch, **variables)
    assert missing in str(error.value)
    assert SECRET not in str(error.value)


@pytest.mark.parametrize(
    "variables",
    [
        {"GESTCONF_EMAIL_PROVIDER": "sendgrid"},
        {
            "GESTCONF_EMAIL_PROVIDER": "brevo",
            "DEFAULT_FROM_EMAIL": "pas une adresse",
            "GESTCONF_BREVO_API_KEY": SECRET,
        },
    ],
)
def test_invalid_provider_or_sender(monkeypatch, variables):
    with pytest.raises(ImproperlyConfigured):
        from_env(monkeypatch, **variables)


@override_settings(GESTCONF_EMAIL_PROVIDER_REQUIRED=True, GESTCONF_EMAIL_PROVIDER="")
def test_web_application_refuses_to_start_without_provider_in_production():
    with pytest.raises(ImproperlyConfigured, match="GESTCONF_EMAIL_PROVIDER"):
        require_email_provider()


@override_settings(GESTCONF_EMAIL_PROVIDER_REQUIRED=True, GESTCONF_EMAIL_PROVIDER="brevo")
def test_web_application_starts_with_a_provider():
    require_email_provider()


def test_outside_production_no_provider_is_required():
    assert settings.GESTCONF_EMAIL_PROVIDER_REQUIRED is False
    require_email_provider()


PROD_ENV = {
    "DJANGO_SETTINGS_MODULE": "config.settings.prod",
    "DJANGO_SECRET_KEY": "ci-only-0123456789abcdefghijklmnopqrstuvwxyz-0123456789",
    "DJANGO_ALLOWED_HOSTS": "conference.exemple.org",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://conference.exemple.org",
    "DATABASE_URL": "sqlite:///:memory:",
    "GESTCONF_ENV_FILE": "/nonexistent/.env",
}


def _load_prod_settings(**variables):
    """Charge config.settings.prod dans un processus neuf (les réglages ne se rechargent pas)."""
    code = (
        "import django; django.setup(); from django.conf import settings; "
        "print(settings.EMAIL_BACKEND, settings.GESTCONF_EMAIL_PROVIDER_REQUIRED)"
    )
    return subprocess.run(  # noqa: S603 (interpréteur courant, code fixe)
        [sys.executable, "-c", code],
        cwd=settings.BASE_DIR,
        env={"PATH": "/usr/bin:/bin", **PROD_ENV, **variables},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_production_settings_fail_at_startup_when_provider_is_incomplete():
    result = _load_prod_settings(GESTCONF_EMAIL_PROVIDER="brevo")
    assert result.returncode != 0
    assert "incomplet" in result.stderr
    assert "GESTCONF_BREVO_API_KEY" in result.stderr


def test_production_settings_load_with_a_complete_provider():
    result = _load_prod_settings(
        GESTCONF_EMAIL_PROVIDER="brevo",
        GESTCONF_BREVO_API_KEY=SECRET,
        DEFAULT_FROM_EMAIL="no-reply@conference.exemple.org",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["anymail.backends.brevo.EmailBackend", "True"]


def test_production_settings_load_without_provider_for_administration():
    """check, migrate et createcachetable restent possibles ; seul le site refuse de démarrer."""
    result = _load_prod_settings()
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == [
        "apps.communications.backends.UnconfiguredEmailBackend",
        "True",
    ]
