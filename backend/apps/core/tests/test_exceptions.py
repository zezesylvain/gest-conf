"""Format d'erreur normalisé {code, message, fields} (étude §9.1)."""

import pytest

pytestmark = [pytest.mark.urls("apps.core.tests.urls"), pytest.mark.django_db]


def assert_error_shape(payload: dict) -> None:
    assert set(payload) == {"code", "message", "fields"}
    assert isinstance(payload["message"], str) and payload["message"]


def test_field_validation_error(client):
    response = client.post("/field-validation", {}, content_type="application/json")
    assert response.status_code == 400
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "validation_error"
    assert list(payload["fields"]) == ["title"]


def test_non_field_validation_error(client):
    response = client.post("/non-field-validation", {}, content_type="application/json")
    assert response.status_code == 400
    payload = response.json()
    assert payload["fields"] == {"non_field_errors": ["Erreur globale"]}


def test_unauthenticated_access(client):
    # Authentification par session uniquement : DRF répond 403 (et non 401).
    response = client.get("/protected")
    assert response.status_code == 403
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "not_authenticated"
    assert payload["fields"] == {}


def test_http404_is_normalized(client):
    response = client.get("/http404")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_django_permission_denied_is_normalized(client):
    response = client.get("/django-permission-denied")
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
