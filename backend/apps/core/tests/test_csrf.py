"""Échec CSRF renvoyé en JSON « csrf_failed » sur les trois chemins (plan L1 §4.6, §12.2).

Le client de test de Django et APIClient désactivent le contrôle CSRF par défaut :
chaque test utilise donc ``enforce_csrf_checks=True``.
"""

import pytest
from django.conf import settings
from django.test import Client

pytestmark = [pytest.mark.urls("apps.core.tests.urls"), pytest.mark.django_db]


def assert_csrf_failed(response) -> None:
    assert response.status_code == 403
    payload = response.json()
    assert payload["code"] == "csrf_failed"
    assert payload["fields"] == {}
    assert payload["message"]


def fetch_csrf_token(client) -> str:
    """Obtient le cookie CSRF comme Angular (GET d'amorçage), et renvoie sa valeur."""
    response = client.get("/csrf-token")
    assert response.status_code == 200
    return client.cookies[settings.CSRF_COOKIE_NAME].value


# --- Cas 1 : vue Django ordinaire (allauth), middleware CSRF → CSRF_FAILURE_VIEW --------


def test_django_view_without_token_gets_json_csrf_failed():
    client = Client(enforce_csrf_checks=True)
    assert_csrf_failed(client.post("/csrf-django-view"))


def test_django_view_with_token_passes():
    client = Client(enforce_csrf_checks=True)
    token = fetch_csrf_token(client)
    response = client.post("/csrf-django-view", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200


def test_csrf_failure_view_is_configured():
    assert settings.CSRF_FAILURE_VIEW == "apps.core.views.csrf_failure"


# --- Cas 2 : vue DRF, session authentifiée → SessionAuthentication.enforce_csrf ---------


def test_authenticated_drf_post_without_token_gets_csrf_failed(csrf_api_client, user):
    csrf_api_client.force_login(user)
    assert_csrf_failed(csrf_api_client.post("/protected", {}, format="json"))


def test_authenticated_drf_post_with_token_passes(csrf_api_client, user):
    csrf_api_client.force_login(user)
    token = fetch_csrf_token(csrf_api_client)
    response = csrf_api_client.post("/protected", {}, format="json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200
    assert response.json() == {"user": user.email}


def test_authenticated_drf_get_is_not_checked(csrf_api_client, user):
    csrf_api_client.force_login(user)
    assert csrf_api_client.get("/protected").status_code == 200


def test_anonymous_drf_post_gets_401_not_csrf(csrf_api_client):
    """Sans session, DRF ne contrôle pas le CSRF : l'absence de session prime (401)."""
    response = csrf_api_client.post("/protected", {}, format="json")
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


# --- Cas 3 : POST DRF anonyme → permission CsrfEnforced --------------------------------


def test_anonymous_post_with_csrf_enforced_without_token_gets_csrf_failed(csrf_api_client):
    assert_csrf_failed(csrf_api_client.post("/csrf-enforced", {}, format="json"))


def test_anonymous_post_with_csrf_enforced_with_token_passes(csrf_api_client):
    token = fetch_csrf_token(csrf_api_client)
    response = csrf_api_client.post("/csrf-enforced", {}, format="json", HTTP_X_CSRFTOKEN=token)
    assert response.status_code == 200


def test_csrf_enforced_rejects_wrong_token(csrf_api_client):
    fetch_csrf_token(csrf_api_client)
    response = csrf_api_client.post("/csrf-enforced", {}, format="json", HTTP_X_CSRFTOKEN="x" * 32)
    assert_csrf_failed(response)


def test_csrf_enforced_rejects_foreign_origin_over_https(csrf_api_client):
    token = fetch_csrf_token(csrf_api_client)
    response = csrf_api_client.post(
        "/csrf-enforced",
        {},
        format="json",
        secure=True,
        HTTP_X_CSRFTOKEN=token,
        HTTP_ORIGIN="https://attaquant.example",
    )
    assert_csrf_failed(response)


def test_csrf_rejection_log_cannot_be_forged(csrf_api_client, caplog):
    """Origin et chemin sont échappés dans le journal (comme log_response de Django).

    Sans échappement, un saut de ligne dans l'en-tête Origin ou dans le chemin
    (%0A, décodé par Django) produirait une fausse ligne de journal.
    """
    token = fetch_csrf_token(csrf_api_client)
    forged = "2026-10-05 INFO forged entry"
    with caplog.at_level("WARNING", logger="django.security.csrf"):
        response = csrf_api_client.post(
            "/csrf-enforced-path/x%0A" + forged.replace(" ", "%20"),
            {},
            format="json",
            secure=True,
            HTTP_X_CSRFTOKEN=token,
            HTTP_ORIGIN="https://evil.example\n" + forged,
        )
    assert_csrf_failed(response)
    messages = [
        record.getMessage() for record in caplog.records if record.name == "django.security.csrf"
    ]
    assert len(messages) == 1
    assert "\n" not in messages[0]
    assert "\r" not in messages[0]
    # Les deux valeurs restent lisibles, sous forme échappée.
    assert messages[0].count("\\n" + forged) == 2
