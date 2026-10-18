"""Réglages d'envoi des e-mails en production (décision D10 amendée : SMTP de l'hébergement).

Les réglages de production se chargent dans un sous-processus, avec un environnement minimal
et sans fichier .env, pour vérifier ce que lit config/settings/prod.py.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
SMTP = "django.core.mail.backends.smtp.EmailBackend"

PROBE = (
    "import json, django; django.setup(); from django.conf import settings as s; "
    "print(json.dumps({k: getattr(s, k) for k in ('EMAIL_BACKEND', 'EMAIL_HOST', "
    "'EMAIL_PORT', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD', 'EMAIL_USE_SSL', "
    "'EMAIL_USE_TLS', 'EMAIL_TIMEOUT')}))"
)


def load_prod_settings(tmp_path, **extra):
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("EMAIL_", "GESTCONF_", "DJANGO_", "DATABASE_"))
    }
    env.update(
        {
            "DJANGO_SETTINGS_MODULE": "config.settings.prod",
            "GESTCONF_ENV_FILE": str(tmp_path / "absent.env"),
            "DJANGO_SECRET_KEY": "x" * 60,
            "DJANGO_ALLOWED_HOSTS": "conference.exemple.org",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://conference.exemple.org",
            "DATABASE_URL": f"sqlite:///{tmp_path / 'db.sqlite3'}",
            "DEFAULT_FROM_EMAIL": "GEST-CONF <no-reply@exemple.org>",
            "GESTCONF_PUBLIC_URL": "https://conference.exemple.org",
            "GESTCONF_MFA_ENCRYPTION_KEYS": "ZmFrZS1rZXktZm9yLXRlc3RzLW9ubHktMzItYnl0ZXM=",
        }
    )
    env.update(extra)
    return subprocess.run(  # noqa: S603 (interpréteur courant, code fixe, sans shell)
        [sys.executable, "-c", PROBE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def smtp_env(**overrides):
    values = {
        "GESTCONF_EMAIL_BACKEND": SMTP,
        "EMAIL_HOST": "mail.exemple.org",
        "EMAIL_PORT": "465",
        "EMAIL_USE_SSL": "true",
        "EMAIL_HOST_USER": "info@exemple.org",
        "EMAIL_HOST_PASSWORD": "p@ss#w=rd:1",
    }
    values.update(overrides)
    return values


def test_smtp_settings_are_read_from_the_environment(tmp_path):
    """D10 amendée : serveur, port, identifiants, chiffrement et délai lus dans l'environnement."""
    result = load_prod_settings(tmp_path, **smtp_env())
    assert result.returncode == 0, result.stderr
    settings = json.loads(result.stdout.strip().splitlines()[-1])
    assert settings == {
        "EMAIL_BACKEND": SMTP,
        "EMAIL_HOST": "mail.exemple.org",
        "EMAIL_PORT": 465,
        "EMAIL_HOST_USER": "info@exemple.org",
        "EMAIL_HOST_PASSWORD": "p@ss#w=rd:1",
        "EMAIL_USE_SSL": True,
        "EMAIL_USE_TLS": False,
        "EMAIL_TIMEOUT": 10.0,
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"EMAIL_HOST_PASSWORD": ""},
        {"EMAIL_HOST_USER": ""},
        {"EMAIL_HOST": "localhost"},
        {"EMAIL_USE_SSL": "false"},
        {"EMAIL_USE_TLS": "true"},
    ],
    ids=["sans-mot-de-passe", "sans-identifiant", "hote-local", "sans-chiffrement", "ssl-et-tls"],
)
def test_smtp_in_production_requires_authenticated_encrypted_sending(tmp_path, overrides):
    """D10 amendée : en production, SMTP authentifié et chiffré (SSL ou TLS, un seul)."""
    result = load_prod_settings(tmp_path, **smtp_env(**overrides))
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "SMTP" in result.stderr


def test_api_provider_ignores_the_smtp_settings(tmp_path):
    """Un fournisseur par API (anymail) ne réclame aucun réglage SMTP."""
    result = load_prod_settings(
        tmp_path,
        GESTCONF_EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        BREVO_API_KEY="cle-de-test",
    )
    assert result.returncode == 0, result.stderr
