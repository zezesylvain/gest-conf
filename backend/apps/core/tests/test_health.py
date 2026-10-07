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
        "jobs": "unknown",
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
    # Battement de cœur illisible sans base : état inconnu, sans nouvelle requête.
    assert response.json()["jobs"] == "unknown"


def test_health_degraded_when_cache_is_down(client, monkeypatch):
    monkeypatch.setattr(views, "cache_is_available", lambda: False)
    response = client.get(reverse("core:health"))
    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "database": "ok",
        "cache": "error",
        "jobs": "unknown",
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


# --- Champ « jobs » : cron de la file de tâches (plan L1 §8.4, arbitrage L1.2) ------------


def _heartbeat(last_success_at):
    from apps.core.models import CronHeartbeat

    CronHeartbeat.objects.update_or_create(
        name="run_jobs", defaults={"last_success_at": last_success_at}
    )


def test_health_jobs_ok_after_recent_run(client):
    from django.utils import timezone

    _heartbeat(timezone.now())
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json()["jobs"] == "ok"
    assert response.json()["status"] == "ok"


def test_health_jobs_late_is_degraded_but_not_an_http_error(client, settings):
    """Un cron en retard ne met pas le site en panne : 200 avec « degraded »."""
    from datetime import timedelta

    from django.utils import timezone

    settings.GESTCONF_CRON_INTERVAL_SECONDS = 60
    _heartbeat(timezone.now() - timedelta(seconds=3 * 60 + 5))
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json()["jobs"] == "late"
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "ok"


def test_health_jobs_late_threshold_is_three_intervals(settings):
    from datetime import timedelta

    from django.utils import timezone

    from apps.core.heartbeat import jobs_status

    settings.GESTCONF_CRON_INTERVAL_SECONDS = 300
    now = timezone.now()
    _heartbeat(now - timedelta(seconds=900))
    assert jobs_status(now=now) == "ok"
    assert jobs_status(now=now + timedelta(seconds=1)) == "late"


def test_health_jobs_unknown_before_first_success(client):
    """Aucun passage réussi (installation neuve) : « unknown », qui ne dégrade pas l'état."""
    _heartbeat(None)
    response = client.get(reverse("core:health"))
    assert response.status_code == 200
    assert response.json()["jobs"] == "unknown"
    assert response.json()["status"] == "ok"


def test_health_jobs_unknown_when_heartbeat_unreadable(monkeypatch):
    from apps.core import heartbeat

    def broken(*args, **kwargs):
        raise DatabaseError("table absente")

    monkeypatch.setattr(heartbeat.CronHeartbeat.objects, "filter", broken)
    assert heartbeat.jobs_status() == "unknown"
