"""File de tâches asynchrones (règle n° 9 de CLAUDE.md, plan L1 §8.1 et §8.2).

Pas de Celery ni de Redis sur l'hébergement mutualisé : une tâche est une ligne
``Job``, exécutée par ``manage.py run_jobs`` lancée par cron.

Exclusivité sans ``SELECT … FOR UPDATE SKIP LOCKED`` (MariaDB ≥ 10.6 seulement,
version d'o2switch inconnue) : un job est **réservé par une mise à jour
conditionnelle** (``status=pending`` → ``running``). Une ligne modifiée signifie
que le job nous appartient ; deux exécutions simultanées (deux cron, ou le cron
et la voie rapide des e-mails) ne traitent donc jamais le même job, même si le
verrou de commande fait défaut.

Livraison « au moins une fois » : chaque gestionnaire est idempotent.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.core.models import Job, JobPriority, JobStatus

logger = logging.getLogger(__name__)

# Délais avant une nouvelle tentative, après la 1re, 2e, 3e puis 4e erreur et au-delà.
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
)
# Bail d'une réservation : au-delà, un job « running » est considéré comme abandonné
# (processus tué, délai de Passenger ou du cron dépassé) et repris.
LEASE_DURATION = timedelta(minutes=15)
# Taille d'un lot de sélection (plan §8.2).
BATCH_SIZE = 20
LAST_ERROR_MAX_LENGTH = 2000

type Handler = Callable[[Job], None]


@dataclass(frozen=True, slots=True)
class JobType:
    kind: str
    handler: Handler
    # Appelé une fois, quand le job passe définitivement en échec (« failed »).
    on_final_failure: Callable[[Job], None] | None = None


_REGISTRY: dict[str, JobType] = {}


def register_job(
    kind: str, *, on_final_failure: Callable[[Job], None] | None = None
) -> Callable[[Handler], Handler]:
    """Déclare le gestionnaire d'un type de tâche.

    Exemple : ``@register_job("communications.send_email")``.
    """

    def decorator(handler: Handler) -> Handler:
        existing = _REGISTRY.get(kind)
        if existing is not None and existing.handler is not handler:
            raise ValueError(f"Type de tâche déjà enregistré : {kind}")
        if len(kind) > Job._meta.get_field("kind").max_length:
            raise ValueError(f"Type de tâche trop long : {kind}")
        _REGISTRY[kind] = JobType(kind, handler, on_final_failure)
        return handler

    return decorator


def registered_kinds() -> frozenset[str]:
    return frozenset(_REGISTRY)


class RetryLater(Exception):
    """Levée par un gestionnaire pour reporter le job sans consommer de tentative.

    Exemple : plafond horaire d'envoi d'e-mails atteint (plan §8.3).
    """

    def __init__(self, run_at: datetime) -> None:
        super().__init__(run_at.isoformat())
        self.run_at = run_at


def worker_id() -> str:
    """Identifiant de l'exécutant, ``hôte:pid`` (colonne ``locked_by``)."""
    return f"{socket.gethostname()}:{os.getpid()}"[-64:]


def _check_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Données du job : JSON simple (identifiants et scalaires), jamais d'objet ORM."""
    try:
        return json.loads(json.dumps(dict(payload), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise TypeError(f"Données de tâche non sérialisables en JSON : {exc}") from exc


def enqueue(
    kind: str,
    payload: Mapping[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    priority: int = JobPriority.NORMAL,
    dedup_key: str | None = None,
    max_attempts: int = 5,
) -> Job:
    """Programme une tâche ; à appeler dans la transaction du service métier.

    Avec ``dedup_key``, une tâche de même clé déjà programmée (quel que soit son
    statut) est renvoyée telle quelle au lieu d'en créer une seconde.
    """
    if kind not in _REGISTRY:
        raise ValueError(f"Type de tâche inconnu : {kind}")
    if max_attempts < 1:
        raise ValueError("max_attempts doit valoir au moins 1.")
    fields = {
        "kind": kind,
        "payload": _check_payload(payload or {}),
        "run_at": run_at or timezone.now(),
        "priority": priority,
        "max_attempts": max_attempts,
        "dedup_key": dedup_key,
    }
    if dedup_key is None:
        return Job.objects.create(**fields)
    existing = Job.objects.filter(dedup_key=dedup_key).first()
    if existing is not None:
        return existing
    try:
        # Point de sauvegarde : une collision concurrente n'annule pas la transaction
        # englobante du service métier.
        with transaction.atomic():
            return Job.objects.create(**fields)
    except IntegrityError:
        return Job.objects.get(dedup_key=dedup_key)


def claim(job_id: int, worker: str) -> bool:
    """Réserve le job s'il est encore en attente et exigible (mise à jour conditionnelle)."""
    now = timezone.now()
    updated = Job.objects.filter(pk=job_id, status=JobStatus.PENDING, run_at__lte=now).update(
        status=JobStatus.RUNNING,
        locked_by=worker,
        locked_at=now,
        attempts=F("attempts") + 1,
    )
    return updated == 1


def _error_text(exc: BaseException) -> str:
    """Nature de l'erreur seulement : le message d'une exception peut contenir une
    adresse ou une donnée personnelle (refus du destinataire, par exemple). Le détail
    complet va dans le journal du serveur (``logger.exception``)."""
    return f"{type(exc).__module__}.{type(exc).__qualname__}"[:LAST_ERROR_MAX_LENGTH]


def retry_delay(attempts: int) -> timedelta:
    return RETRY_DELAYS[min(max(attempts, 1), len(RETRY_DELAYS)) - 1]


def _finalize_failure(job: Job, error: str) -> None:
    """Le job est définitivement en échec : rappel du type de tâche, alerte aux opérateurs."""
    job_type = _REGISTRY.get(job.kind)
    if job_type is not None and job_type.on_final_failure is not None:
        try:
            job_type.on_final_failure(job)
        except Exception:
            logger.exception("Rappel d'échec de la tâche %s#%s en erreur", job.kind, job.pk)
    from apps.core.alerts import notify_operators

    notify_operators(
        "Tâche en échec définitif",
        {"tâche": f"{job.kind}#{job.pk}", "tentatives": str(job.attempts), "erreur": error},
    )


def _record_failure(job: Job, worker: str, exc: BaseException) -> None:
    error = _error_text(exc)
    now = timezone.now()
    mine = Job.objects.filter(pk=job.pk, status=JobStatus.RUNNING, locked_by=worker)
    if job.attempts >= job.max_attempts:
        mine.update(
            status=JobStatus.FAILED,
            finished_at=now,
            last_error=error,
            locked_at=None,
            locked_by="",
        )
        job.refresh_from_db()
        _finalize_failure(job, error)
    else:
        mine.update(
            status=JobStatus.PENDING,
            run_at=now + retry_delay(job.attempts),
            last_error=error,
            locked_at=None,
            locked_by="",
        )


def execute(job_id: int, worker: str) -> JobStatus | None:
    """Exécute un job **déjà réservé** par ``worker`` ; renvoie son nouveau statut."""
    job = Job.objects.filter(pk=job_id, status=JobStatus.RUNNING, locked_by=worker).first()
    if job is None:
        return None
    mine = Job.objects.filter(pk=job.pk, status=JobStatus.RUNNING, locked_by=worker)
    job_type = _REGISTRY.get(job.kind)
    try:
        if job_type is None:
            raise LookupError(f"Type de tâche inconnu : {job.kind}")
        job_type.handler(job)
    except RetryLater as deferral:
        # Report sans échec : la tentative n'est pas décomptée.
        mine.update(
            status=JobStatus.PENDING,
            run_at=max(deferral.run_at, timezone.now()),
            attempts=F("attempts") - 1,
            locked_at=None,
            locked_by="",
        )
        return JobStatus.PENDING
    except Exception as exc:
        logger.exception("Tâche %s#%s en erreur (tentative %s)", job.kind, job.pk, job.attempts)
        if isinstance(exc, LookupError) and job_type is None:
            job.max_attempts = job.attempts  # inutile de réessayer un type inconnu
        _record_failure(job, worker, exc)
        return _status_of(job.pk)
    mine.update(
        status=JobStatus.SUCCEEDED,
        finished_at=timezone.now(),
        last_error="",
        locked_at=None,
        locked_by="",
    )
    return JobStatus.SUCCEEDED


def _status_of(job_id: int) -> JobStatus:
    return JobStatus(Job.objects.values_list("status", flat=True).get(pk=job_id))


def try_run_now(job_id: int) -> JobStatus | None:
    """Tente d'exécuter tout de suite un job exigible (voie rapide des e-mails, plan §8.3).

    Même réservation conditionnelle que le cron : aucun doublon possible. Ne lève
    jamais : en cas d'échec, le job reste en file et le cron prend le relais.
    """
    worker = worker_id()
    try:
        if not claim(job_id, worker):
            return None
        return execute(job_id, worker)
    except Exception:
        logger.exception("Exécution immédiate de la tâche #%s impossible", job_id)
        return None


def recover_stale(now: datetime | None = None) -> int:
    """Reprend les jobs ``running`` dont le bail est dépassé (plan §8.2, étape 3)."""
    now = now or timezone.now()
    stale = Job.objects.filter(status=JobStatus.RUNNING, locked_at__lt=now - LEASE_DURATION)
    count = 0
    for job in stale:
        guard = Job.objects.filter(pk=job.pk, status=JobStatus.RUNNING, locked_at=job.locked_at)
        error = "apps.core.jobs.LeaseExpired"
        if job.attempts >= job.max_attempts:
            if guard.update(
                status=JobStatus.FAILED,
                finished_at=now,
                last_error=error,
                locked_at=None,
                locked_by="",
            ):
                job.refresh_from_db()
                _finalize_failure(job, error)
                count += 1
        elif guard.update(
            status=JobStatus.PENDING,
            run_at=now,
            last_error=error,
            locked_at=None,
            locked_by="",
        ):
            count += 1
    return count


def run_pending(*, deadline: float, worker: str | None = None, batch_size: int = BATCH_SIZE) -> int:
    """Traite les jobs exigibles jusqu'à épuisement ou jusqu'à ``deadline`` (``time.monotonic``).

    Renvoie le nombre de jobs exécutés (réussis ou non).
    """
    worker = worker or worker_id()
    processed = 0
    while time.monotonic() < deadline:
        candidates = list(
            Job.objects.filter(status=JobStatus.PENDING, run_at__lte=timezone.now())
            .order_by("priority", "run_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        if not candidates:
            break
        progressed = False
        for job_id in candidates:
            if time.monotonic() >= deadline:
                break
            if claim(job_id, worker):
                execute(job_id, worker)
                processed += 1
                progressed = True
        if not progressed:
            break  # tout le lot a été pris par un autre exécutant
    return processed
