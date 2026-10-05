"""Messages d'erreur de l'API dans la langue de la requête (plan L1 §4.2, §11).

Sources en français (LANGUAGE_CODE), catalogue « en » dans backend/locale.
"""

from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

pytestmark = pytest.mark.django_db


def test_locale_middleware_position():
    """Après SessionMiddleware, avant CommonMiddleware (documentation de Django)."""
    middleware = settings.MIDDLEWARE
    locale = middleware.index("django.middleware.locale.LocaleMiddleware")
    assert middleware.index("django.contrib.sessions.middleware.SessionMiddleware") < locale
    assert locale < middleware.index("django.middleware.common.CommonMiddleware")


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Resource not found."),
        ("fr", "Ressource introuvable."),
        ("", "Ressource introuvable."),
    ],
)
def test_not_found_message_follows_accept_language(client, language, expected):
    response = client.get("/v1/inconnu", HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 404
    assert response.json() == {"code": "not_found", "message": expected, "fields": {}}
    assert response["Content-Language"] == (language or "fr")


CSRF_MESSAGES = [
    ("en-US,en;q=0.9", "CSRF verification failed: reload the page and try again."),
    ("fr-FR,fr;q=0.9", "Échec de la vérification CSRF : rechargez la page puis réessayez."),
]


@pytest.mark.urls("apps.core.tests.urls")
@pytest.mark.parametrize(("language", "expected"), CSRF_MESSAGES)
def test_csrf_failure_view_message_is_translated(language, expected):
    client = Client(enforce_csrf_checks=True)
    response = client.post("/csrf-django-view", HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 403
    assert response.json()["message"] == expected


@pytest.mark.urls("apps.core.tests.urls")
@pytest.mark.parametrize(("language", "expected"), CSRF_MESSAGES)
def test_csrf_failed_drf_message_is_translated(csrf_api_client, language, expected):
    response = csrf_api_client.post("/csrf-enforced", {}, HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 403
    assert response.json()["message"] == expected


@pytest.mark.urls("apps.core.tests.urls")
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "Authentication credentials were not provided."),
        ("fr", "Informations d'authentification non fournies."),
    ],
)
def test_drf_messages_are_translated(client, language, expected):
    """Les messages de DRF viennent de son propre catalogue (français fourni par DRF)."""
    response = client.get("/protected", HTTP_ACCEPT_LANGUAGE=language)
    assert response.status_code == 401
    assert response.json()["message"] == expected


def test_compiled_catalogue_is_versioned():
    """Les .mo sont versionnés : gettext n'est pas garanti sur l'hébergement (plan L1 §11)."""
    locale_dir = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES"
    assert [Path(settings.BASE_DIR) / "locale"] == settings.LOCALE_PATHS
    po, mo = locale_dir / "django.po", locale_dir / "django.mo"
    assert po.is_file() and mo.is_file()
    assert mo.stat().st_size > 0


@pytest.mark.urls("apps.core.tests.urls")
@pytest.mark.parametrize(
    ("path", "language", "expected"),
    [
        ("/domain-error/not-allowed", "en", "Action not allowed."),
        ("/domain-error/not-allowed", "fr", "Action non autorisée."),
        ("/domain-error/invalid", "en", "Invalid data."),
        ("/field-validation", "en", "Invalid data."),
        ("/domain-error/quota", "en", "Quota reached. Expected available in 43 seconds."),
    ],
)
def test_domain_error_messages_are_translated(client, path, language, expected):
    response = client.generic(
        "POST" if path == "/field-validation" else "GET",
        path,
        "{}",
        content_type="application/json",
        HTTP_ACCEPT_LANGUAGE=language,
    )
    assert response.json()["message"] == expected
