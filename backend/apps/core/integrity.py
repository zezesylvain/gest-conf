"""Contrôles d'intégrité quotidiens (``manage.py check_integrity``, plan L1 §8.4).

Chaque application déclare ses contrôles dans ``AppConfig.ready()`` ; ``core`` ne
dépend d'aucune application métier. Un contrôle renvoie la liste de ses anomalies,
**sans donnée personnelle** (identifiants techniques et nombres seulement) : elles
partent par e-mail aux opérateurs. Lecture seule, donc idempotent.
"""

from __future__ import annotations

from collections.abc import Callable

from django.db import connection

from apps.core.models import Job, JobStatus

type IntegrityCheck = Callable[[], list[str]]

_CHECKS: dict[str, IntegrityCheck] = {}

# Plan §3.5 : alerte au-delà de 20 000 entrées dans le cache partagé (risque R18).
CACHE_ALERT_THRESHOLD = 20_000


def register_integrity_check(name: str, check: IntegrityCheck) -> None:
    existing = _CHECKS.get(name)
    if existing is not None and existing is not check:
        raise ValueError(f"Contrôle d'intégrité déjà enregistré : {name}")
    _CHECKS[name] = check


def integrity_checks() -> list[tuple[str, IntegrityCheck]]:
    return sorted(_CHECKS.items())


def check_cache_size() -> list[str]:
    from django.conf import settings

    table = settings.CACHES["default"]["LOCATION"]
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)}")  # noqa: S608
        count = cursor.fetchone()[0]
    if count > CACHE_ALERT_THRESHOLD:
        return [f"Cache partagé : {count} entrées (seuil {CACHE_ALERT_THRESHOLD})."]
    return []


def check_failed_jobs() -> list[str]:
    count = Job.objects.filter(status=JobStatus.FAILED).count()
    return [f"Tâches en échec : {count} (manage.py outbox, run_jobs)."] if count else []
