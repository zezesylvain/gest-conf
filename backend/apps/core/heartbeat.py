"""Battements de cœur des commandes d'exploitation et état du cron (plan L1 §8.2, §8.4).

Les commandes lancées par le cron ne sont pas auditées à chaque passage (arbitrage L1.2) :
leur trace est la ligne ``CronHeartbeat`` mise à jour au début et à la fin de chaque passage.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.db import DatabaseError
from django.utils import timezone

from apps.core.models import CronHeartbeat, HeartbeatStatus
from apps.core.serializers import JobsStatus

# Nom du battement de cœur lu par /health (commande run_jobs).
RUN_JOBS = "run_jobs"
# « late » : dernier succès plus vieux que ce nombre d'intervalles du cron (plan §8.4).
LATE_AFTER_INTERVALS = 3


def beat_start(name: str, *, now: datetime | None = None) -> datetime:
    """Note le démarrage d'un passage ; renvoie l'instant de démarrage."""
    now = now or timezone.now()
    CronHeartbeat.objects.get_or_create(name=name)
    CronHeartbeat.objects.filter(name=name).update(
        last_started_at=now, last_status=HeartbeatStatus.RUNNING, updated_at=now
    )
    return now


def beat_finish(
    name: str,
    *,
    started_at: datetime,
    succeeded: bool,
    processed: int = 0,
    error: str = "",
    summary: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    """Note la fin d'un passage : statut, durée, nombre d'éléments traités, résumé."""
    now = now or timezone.now()
    duration_ms = max(0, int((now - started_at).total_seconds() * 1000))
    fields: dict[str, Any] = {
        "last_finished_at": now,
        "last_status": HeartbeatStatus.SUCCEEDED if succeeded else HeartbeatStatus.FAILED,
        "last_duration_ms": duration_ms,
        "processed_count": processed,
        "last_error": error,
        "summary": summary,
        "updated_at": now,
    }
    if succeeded:
        fields["last_success_at"] = now
    CronHeartbeat.objects.filter(name=name).update(**fields)


def cron_interval() -> timedelta:
    return timedelta(seconds=settings.GESTCONF_CRON_INTERVAL_SECONDS)


def jobs_status(*, now: datetime | None = None) -> JobsStatus:
    """État du cron de ``run_jobs`` pour ``/health`` : ``ok``, ``late`` ou ``unknown``.

    ``unknown`` : aucun passage réussi enregistré (installation neuve) ou base illisible.
    """
    try:
        last_success = (
            CronHeartbeat.objects.filter(name=RUN_JOBS)
            .values_list("last_success_at", flat=True)
            .first()
        )
    except DatabaseError:
        return JobsStatus.UNKNOWN
    if last_success is None:
        return JobsStatus.UNKNOWN
    now = now or timezone.now()
    if now - last_success > LATE_AFTER_INTERVALS * cron_interval():
        return JobsStatus.LATE
    return JobsStatus.OK
