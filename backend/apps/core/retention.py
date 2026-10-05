"""Tâches de conservation et de purge exécutées par ``manage.py cleanup`` (plan L1 §8.4, D15).

Chaque application déclare ses purges dans ``AppConfig.ready()`` avec
``register_retention_task`` : ``core`` ne dépend ainsi d'aucune application
métier, et chaque lot ajoute les siennes (invitations en L1.5, données
d'édition en L8...).

Deux familles :

- ``security=True`` : purge imposée par la sécurité, appliquée dans tous les
  cas (par exemple les corps d'e-mails contenant un lien à jeton, plan §3.6) ;
- sinon, durée de conservation proposée par D15 et **non encore validée** par le
  commanditaire : simulation seule (comptage) tant que
  ``GESTCONF_RETENTION_ENFORCED`` est faux.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from apps.core.models import Job, JobStatus

# (dry_run, now) -> nombre de lignes concernées (purgées, ou à purger en simulation).
type RetentionFunction = Callable[[bool, datetime], int]


@dataclass(frozen=True, slots=True)
class RetentionTask:
    name: str
    function: RetentionFunction
    security: bool = False


_TASKS: dict[str, RetentionTask] = {}


def register_retention_task(
    name: str, function: RetentionFunction, *, security: bool = False
) -> None:
    existing = _TASKS.get(name)
    if existing is not None and existing.function is not function:
        raise ValueError(f"Tâche de conservation déjà enregistrée : {name}")
    _TASKS[name] = RetentionTask(name, function, security)


def retention_tasks() -> list[RetentionTask]:
    return [_TASKS[name] for name in sorted(_TASKS)]


# --- Tâches propres au socle ------------------------------------------------------------

# D15 : tâches terminées conservées 30 jours.
FINISHED_JOB_RETENTION = timedelta(days=30)


def purge_finished_jobs(dry_run: bool, now: datetime) -> int:
    finished = Job.objects.filter(
        status__in=(JobStatus.SUCCEEDED, JobStatus.CANCELLED, JobStatus.FAILED),
        finished_at__lt=now - FINISHED_JOB_RETENTION,
    )
    if dry_run:
        return finished.count()
    deleted, _per_model = finished.delete()
    return deleted


# D15 : IP et navigateur du journal effacés après 6 mois ; lignes supprimées après 3 ans.
AUDIT_NETWORK_RETENTION = timedelta(days=183)
AUDIT_ROW_RETENTION = timedelta(days=3 * 365)


def purge_audit_network(dry_run: bool, now: datetime) -> int:
    from apps.core.actor import Actor
    from apps.core.models import AuditLog

    date = now - AUDIT_NETWORK_RETENTION
    if dry_run:
        return AuditLog.objects.filter(at__lt=date).exclude(ip__isnull=True, user_agent="").count()
    return AuditLog.purge_network_before(date, actor=Actor.system("cron:cleanup"))


def purge_audit_rows(dry_run: bool, now: datetime) -> int:
    from apps.core.actor import Actor
    from apps.core.models import AuditLog

    date = now - AUDIT_ROW_RETENTION
    if dry_run:
        return AuditLog.objects.filter(at__lt=date).count()
    return AuditLog.purge_before(date, actor=Actor.system("cron:cleanup"))
