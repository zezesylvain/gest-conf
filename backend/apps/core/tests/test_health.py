import pytest
from django.core.cache import caches
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
        "cache": "ok",
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
    # Le cache est en base : il ne peut pas fonctionner sans elle.
    assert response.json()["cache"] == "error"


def test_health_degraded_when_cache_is_down(client, monkeypatch):
    monkeypatch.setattr(views, "cache_is_available", lambda: False)
    response = client.get(reverse("core:health"))
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "ok",
        "cache": "error",
        "secure": False,
        "release": "dev",
    }


def test_database_is_available_handles_errors(monkeypatch):
    def broken_cursor():
        raise DatabaseError("connexion refusée")

    monkeypatch.setattr(views.connection, "cursor", broken_cursor)
    assert views.database_is_available() is False


@pytest.mark.mariadb
def test_cache_is_available_uses_shared_database_caches():
    """La sonde passe par les vrais DatabaseCache et ne laisse aucune entrée derrière elle."""
    from django.core.cache.backends.db import DatabaseCache

    assert views.HEALTH_CACHE_ALIASES == ("default", "throttle")
    for alias in views.HEALTH_CACHE_ALIASES:
        assert isinstance(caches[alias], DatabaseCache)
    assert views.cache_is_available() is True
    with views.connection.cursor() as cursor:
        for table in ("gestconf_cache", "gestconf_throttle_cache"):
            cursor.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608 (nom fixe)
            assert cursor.fetchone()[0] == 0


@pytest.mark.parametrize("alias", ["default", "throttle"])
def test_cache_is_available_handles_errors(monkeypatch, alias):
    def broken_set(*args, **kwargs):
        raise DatabaseError("table de cache absente")

    monkeypatch.setattr(caches[alias], "set", broken_set)
    assert views.cache_is_available() is False


@pytest.mark.parametrize("alias", ["default", "throttle"])
def test_cache_is_available_detects_wrong_value(monkeypatch, alias):
    monkeypatch.setattr(caches[alias], "get", lambda *args, **kwargs: "autre valeur")
    assert views.cache_is_available() is False


def test_cache_probe_is_memoized_per_process(client, monkeypatch):
    """/health public et sans limite : la sonde n'écrit dans le cache qu'une fois par période.

    Sans cette mémoire, chaque appel anonyme coûterait plusieurs écritures en base
    (amplificateur de charge sur l'hébergement mutualisé).
    """
    calls = []

    def probe() -> bool:
        calls.append(1)
        return True

    clock = [1000.0]
    monkeypatch.setattr(views, "cache_is_available", probe)
    monkeypatch.setattr(views.time, "monotonic", lambda: clock[0])
    for _ in range(20):
        assert client.get(reverse("core:health")).json()["cache"] == "ok"
    assert len(calls) == 1
    clock[0] += views.HEALTH_CACHE_PROBE_TTL - 0.1
    client.get(reverse("core:health"))
    assert len(calls) == 1
    clock[0] += 0.2
    client.get(reverse("core:health"))
    assert len(calls) == 2


def test_cache_probe_ttl_is_short():
    """Une panne du cache doit apparaître vite dans la supervision."""
    assert 0 < views.HEALTH_CACHE_PROBE_TTL <= 30


def test_cache_probe_failure_is_reported_until_it_expires(client, monkeypatch):
    clock = [1000.0]
    state = {"ok": False}
    monkeypatch.setattr(views, "cache_is_available", lambda: state["ok"])
    monkeypatch.setattr(views.time, "monotonic", lambda: clock[0])
    assert client.get(reverse("core:health")).status_code == 503
    state["ok"] = True
    assert client.get(reverse("core:health")).status_code == 503
    clock[0] += views.HEALTH_CACHE_PROBE_TTL
    assert client.get(reverse("core:health")).status_code == 200
