"""Cache partagé en base (plan L1 §3.5, §4.2)."""

import pytest
from django.conf import settings
from django.core.cache import cache, caches
from django.core.cache.backends.db import DatabaseCache
from django.core.management import call_command
from django.db import connection


@pytest.mark.parametrize(
    ("alias", "table"), [("default", "gestconf_cache"), ("throttle", "gestconf_throttle_cache")]
)
def test_cache_settings(alias, table):
    """DatabaseCache en base ; 50 000 entrées avant purge (§3.5).

    Deux tables : les compteurs DRF (« throttle ») sont isolés des clés de sécurité
    (« default ») pour qu'une inondation de compteurs ne puisse pas les purger (R18).
    """
    config = settings.CACHES[alias]
    assert config["BACKEND"] == "django.core.cache.backends.db.DatabaseCache"
    assert config["LOCATION"] == table
    assert config["OPTIONS"] == {"MAX_ENTRIES": 50000, "CULL_FREQUENCY": 3}


def test_cache_tables_are_distinct():
    assert set(settings.CACHES) == {"default", "throttle"}
    assert settings.CACHES["default"]["LOCATION"] != settings.CACHES["throttle"]["LOCATION"]


@pytest.mark.django_db
@pytest.mark.mariadb
def test_cache_round_trip_and_add_semantics():
    """« add » n'écrase pas une clé existante : base de l'anti-rejeu TOTP (L1.6)."""
    assert isinstance(caches["default"], DatabaseCache)
    assert caches["default"]._max_entries == 50000
    cache.set("cle", {"valeur": 1}, timeout=30)
    assert cache.get("cle") == {"valeur": 1}
    assert cache.add("cle", "autre", timeout=30) is False
    assert cache.get("cle") == {"valeur": 1}
    assert cache.add("nouvelle", "x", timeout=30) is True


@pytest.mark.django_db
def test_createcachetable_is_idempotent():
    """Relancée à chaque déploiement : sans effet si les tables existent déjà ; crée les deux."""
    call_command("createcachetable", verbosity=0)
    call_command("createcachetable", verbosity=0)
    tables = connection.introspection.table_names()
    assert {"gestconf_cache", "gestconf_throttle_cache"} <= set(tables)


@pytest.mark.django_db
@pytest.mark.mariadb
def test_throttle_counters_cannot_cull_default_cache():
    """R18 : une inondation de compteurs DRF ne purge jamais les clés du cache « default ».

    Le plafond de la table des compteurs est abaissé à 5 entrées le temps du test :
    au-delà, Django y purge un tiers des clés par ordre alphabétique. Une clé
    « allauth… » (qui se trie avant « throttle_… ») survit dans l'autre table.
    """
    from apps.core.throttling import ScopedRateThrottle

    throttle_cache = caches["throttle"]
    cache.set("allauth:rl:login:198.51.100.1", [1.0], timeout=300)
    original = throttle_cache._max_entries
    throttle_cache._max_entries = 5
    try:
        for index in range(30):
            ScopedRateThrottle.cache.set(f"throttle_invitation_203.0.113.{index}", [1.0], 300)
    finally:
        throttle_cache._max_entries = original
    assert cache.get("allauth:rl:login:198.51.100.1") == [1.0]
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM gestconf_throttle_cache")
        assert cursor.fetchone()[0] < 30  # la purge a bien eu lieu dans la table dédiée
        cursor.execute(
            "SELECT COUNT(*) FROM gestconf_cache WHERE cache_key LIKE %s", ["%throttle%"]
        )
        assert cursor.fetchone()[0] == 0
