"""Purge des entrées expirées des caches en base (plan L1 §3.5, §8.2 étape 4, §16 point 4).

``DatabaseCache`` ne supprime les entrées expirées que lors d'une purge
(``_cull``), déclenchée au-delà de ``MAX_ENTRIES``, qui supprime ensuite un tiers
des clés restantes par ordre alphabétique (risque R18). Supprimer régulièrement
les entrées expirées garde les tables petites et éloigne ce seuil. Django n'offre
pas d'API publique pour cela (``_cull`` est privée) : même requête que ``_cull``.
"""

from __future__ import annotations

from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connections, router
from django.utils import timezone

# Les deux tables créées par « createcachetable » (config/settings/base.py, CACHES).
DATABASE_CACHE_ALIASES = ("default", "throttle")


def purge_expired_cache_entries() -> dict[str, int]:
    """Supprime les entrées expirées de chaque cache en base ; renvoie le nombre par alias."""
    deleted: dict[str, int] = {}
    now = timezone.now().replace(microsecond=0)
    for alias in DATABASE_CACHE_ALIASES:
        store = caches[alias]
        if not isinstance(store, DatabaseCache):
            continue
        db = router.db_for_write(store.cache_model_class)
        connection = connections[db]
        table = connection.ops.quote_name(store._table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {table} WHERE {connection.ops.quote_name('expires')} < %s",  # noqa: S608
                [connection.ops.adapt_datetimefield_value(now)],
            )
            deleted[alias] = max(cursor.rowcount, 0)
    return deleted
