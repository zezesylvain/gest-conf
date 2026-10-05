import pytest
from django.db import DatabaseError
from django.urls import reverse

from apps.core import views

pytestmark = pytest.mark.django_db


def test_health_url_is_relative_to_mount_point():
    # Monté sous /api en production : l'URL publique est /api/v1/health.
    assert reverse("core:health") == "/v1/health"


def test_health_ok_without_authentication(client):
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "secure": False,
        "release": "dev",
    }


def test_health_reports_https(client):
    response = client.get(reverse("core:health"), secure=True)
    assert response.json()["secure"] is True


def test_health_degraded_when_database_is_down(client, monkeypatch):
    monkeypatch.setattr(views, "database_is_available", lambda: False)
    response = client.get(reverse("core:health"))
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "error"


def test_database_is_available_handles_errors(monkeypatch):
    def broken_cursor():
        raise DatabaseError("connexion refusée")

    monkeypatch.setattr(views.connection, "cursor", broken_cursor)
    assert views.database_is_available() is False
