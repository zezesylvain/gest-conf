"""Limitation de débit par portée (plan L1 §4.7), sur le cache partagé en base."""

import threading

import pytest
from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connection, connections
from django.test import Client
from rest_framework.throttling import ScopedRateThrottle

from apps.core.tests.urls import THROTTLE_TEST_SCOPE
from apps.core.throttling import ScopedRateThrottle as GestconfScopedRateThrottle

pytestmark = [pytest.mark.urls("apps.core.tests.urls"), pytest.mark.django_db]


@pytest.fixture
def test_scope_rate(monkeypatch):
    """Taux de la portée de test : 2 requêtes par minute.

    ``ScopedRateThrottle.THROTTLE_RATES`` est le dictionnaire des réglages, lu à
    l'import de DRF : on y ajoute la portée le temps du test.
    """
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, THROTTLE_TEST_SCOPE, "2/min")


def test_throttle_settings_are_scoped_only():
    """Pas de limite globale anon/user (inopérante en L0) : seulement des portées DRF."""
    config = settings.REST_FRAMEWORK
    assert config["DEFAULT_THROTTLE_CLASSES"] == ["apps.core.throttling.ScopedRateThrottle"]
    assert config["DEFAULT_THROTTLE_RATES"] == {
        "invitation": "10/min",
        "invitation_link": "3/hour",
        "invitation_create": "20/hour",
        "data_export": "3/hour",
        "account_deletion": "3/hour",
        "portal_upload": "60/hour",
    }


@pytest.mark.mariadb
def test_scoped_throttle_returns_429_throttled_with_retry_after(client, test_scope_rate):
    assert client.get("/throttled").status_code == 200
    assert client.get("/throttled").status_code == 200
    response = client.get("/throttled")
    assert response.status_code == 429
    assert int(response["Retry-After"]) > 0
    payload = response.json()
    assert payload["code"] == "throttled"
    assert payload["fields"] == {}
    assert payload["message"]


@pytest.mark.mariadb
def test_throttle_counters_are_per_client_ip(client, test_scope_rate):
    for _ in range(2):
        assert client.get("/throttled", REMOTE_ADDR="192.0.2.1").status_code == 200
    assert client.get("/throttled", REMOTE_ADDR="192.0.2.1").status_code == 429
    assert client.get("/throttled", REMOTE_ADDR="192.0.2.2").status_code == 200


def test_throttle_class_uses_the_dedicated_cache():
    """Compteurs DRF dans la table « throttle », isolée des clés de sécurité (R18)."""
    assert issubclass(GestconfScopedRateThrottle, ScopedRateThrottle)
    assert GestconfScopedRateThrottle.cache._alias == "throttle"
    assert isinstance(caches["throttle"], DatabaseCache)


@pytest.mark.mariadb
@pytest.mark.django_db(transaction=True)
def test_throttle_counter_is_shared_between_connections(client, test_scope_rate):
    """Deux processus Passenger = deux connexions à la base : le compteur leur est commun.

    Plan §12.3. Le second « processus » est un fil d'exécution, qui reçoit sa propre
    connexion (les connexions de Django sont propres à chaque fil). Un fil partage
    cependant la mémoire du processus : un LocMemCache réussirait aussi le 429. Le
    partage est donc constaté **dans la base**, par la connexion du fil, qui doit y
    lire la ligne du compteur écrite par la connexion principale ; et le cache doit
    être un DatabaseCache. Les écritures sont validées (transaction=True) : la table
    des compteurs est vidée à la fin, n'étant pas réinitialisée entre les tests.
    """
    throttle_cache = caches["throttle"]
    assert isinstance(throttle_cache, DatabaseCache)
    table = connection.ops.quote_name(throttle_cache._table)
    pattern = f"%throttle_{THROTTLE_TEST_SCOPE}_%"
    seen = {}

    def other_process() -> None:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT cache_key FROM {table} WHERE cache_key LIKE %s",  # noqa: S608
                    [pattern],
                )
                seen["rows"] = [row[0] for row in cursor.fetchall()]
            seen["connection"] = connection.connection
            seen["status"] = Client().get("/throttled").status_code
        finally:
            connections.close_all()

    try:
        assert client.get("/throttled").status_code == 200
        assert client.get("/throttled").status_code == 200
        thread = threading.Thread(target=other_process)
        thread.start()
        thread.join()
        assert seen["connection"] is not connection.connection
        # Le compteur est une ligne de la table, visible d'une autre connexion.
        assert len(seen["rows"]) == 1
        assert seen["rows"][0].endswith(f"throttle_{THROTTLE_TEST_SCOPE}_127.0.0.1")
        assert seen["status"] == 429
    finally:
        throttle_cache.clear()


def test_views_without_scope_are_not_throttled(client):
    for _ in range(30):
        assert client.get("/http404").status_code == 404
