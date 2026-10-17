"""Contrôles d'intégrité quotidiens (``manage.py check_integrity``, plan L1 §8.4).

Chaque application déclare ses contrôles dans ``AppConfig.ready()`` ; ``core`` ne
dépend d'aucune application métier. Un contrôle renvoie la liste de ses anomalies,
**sans donnée personnelle** (identifiants techniques et nombres seulement) : elles
partent par e-mail aux opérateurs. Lecture seule, donc idempotent.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

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


def check_backup_age() -> list[str]:
    """Plan L9, S4 : aucune sauvegarde réussie depuis ``GESTCONF_BACKUP_MAX_AGE_HOURS``."""
    from django.conf import settings
    from django.utils import timezone

    from apps.core.backups import latest_backup_success

    if not settings.GESTCONF_STORAGE_MONITORING:
        return []
    last = latest_backup_success()
    if last is None:
        return ["Aucune sauvegarde réussie enregistrée (cron backup_db, deploy/README.md)."]
    limit = settings.GESTCONF_BACKUP_MAX_AGE_HOURS
    age = timezone.now() - last
    if age > timedelta(hours=limit):
        hours = int(age.total_seconds() // 3600)
        return [f"Dernière sauvegarde réussie il y a {hours} h (seuil : {limit} h)."]
    return []


def check_disk_space() -> list[str]:
    """Plan L9, S4 : espace libre sous ``GESTCONF_DISK_FREE_MIN_MB`` (Mio) sur le disque des
    fichiers déposés ou des sauvegardes. Mesure du système de fichiers : un quota propre au
    compte d'hébergement (CloudLinux) n'y apparaît pas."""
    from django.conf import settings

    if not settings.GESTCONF_STORAGE_MONITORING:
        return []
    minimum = settings.GESTCONF_DISK_FREE_MIN_MB
    problems: list[str] = []
    for label, setting in (
        ("fichiers", "GESTCONF_FILES_DIR"),
        ("sauvegardes", "GESTCONF_BACKUP_DIR"),
    ):
        path = Path(getattr(settings, setting))
        while not path.exists() and path != path.parent:
            path = path.parent
        free = shutil.disk_usage(path).free // (1024 * 1024)
        if free < minimum:
            problems.append(
                f"Espace libre : {free} Mio sur le disque des {label} (seuil : {minimum})."
            )
    return problems
