"""File de tâches en base, sans Celery ni Redis (règle n° 9, plan L1 §8.1 et §8.2).

- ``@register_job("app.verbe")`` enregistre le gestionnaire d'un type de tâche ;
- ``enqueue(...)`` crée la tâche **dans la transaction de l'appelant** (une action
  annulée ne laisse aucune tâche, schéma *transactional outbox*) ;
- ``run_job(id, worker=...)`` réserve une tâche par une **mise à jour conditionnelle**
  (``UPDATE … WHERE status='pending'``) puis l'exécute. Une seule mise à jour peut
  réussir : deux exécutions simultanées (deux cron, ou le cron et la voie rapide) ne
  traitent jamais la même tâche, même sans verrou de commande. Aucun ``SKIP LOCKED``
  (MariaDB ≥ 10.6 seulement, version d'o2switch inconnue) ;
- ``process_jobs(...)`` boucle sur les tâches éligibles dans un budget de temps ;
- ``recover_stale_jobs(...)`` remet en file les tâches dont le bail (15 min) a expiré.

Livraison « au moins une fois » : chaque gestionnaire est idempotent. Il s'exécute hors
transaction (mode autocommit) et gère lui-même ses transactions ; il peut lever
``JobDeferred`` pour reporter la tâche sans consommer de tentative (plafond d'envoi).
Après ``max_attempts`` échecs, la tâche passe en ``failed`` et les opérateurs sont alertés.
"""

from __future__ import annotations

import logging
import os
import re
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.alerts import send_operator_alert
from apps.core.audit import contains_clear_email, mask_email
from apps.core.models import Job, JobStatus

logger = logging.getLogger(__name__)

# Bail d'une tâche réservée : au-delà, elle est considérée comme abandonnée (plan §8.2).
JOB_LEASE = timedelta(minutes=15)
# Nombre de tâches sélectionnées à chaque tour de boucle (plan §8.2).
BATCH_SIZE = 20
# Délais avant nouvelle tentative, selon le rang de l'échec : 1 min, 5 min, 30 min, 2 h.
RETRY_DELAYS: tuple[timedelta, ...] = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
)
LAST_ERROR_MAX_LENGTH = 2000
WORKER_MAX_LENGTH = 64
DEDUP_KEY_MAX_LENGTH = 128
KIND_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_.]*$")
KIND_MAX_LENGTH = 64
# Fragments de noms de clés interdits dans les données d'une tâche (jamais de secret).
FORBIDDEN_PAYLOAD_KEY_PARTS = ("password", "secret", "token")
# Adresse e-mail complète, pour la masquer dans les messages d'erreur conservés.
_EMAIL_IN_TEXT = re.compile(r"[^\s@<>\"'(),;:\[\]]+@[^\s@<>\"'(),;:\[\]]+")


class JobOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    RETRY = "retry"
    FAILED = "failed"
    DEFERRED = "deferred"


class JobDeferred(Exception):
    """Levée par un gestionnaire pour reporter la tâche à ``run_at`` sans consommer de tentative."""

    def __init__(self, run_at: datetime, reason: str = "") -> None:
        super().__init__(reason or "reportée")
        self.run_at = run_at
        self.reason = reason


@dataclass(frozen=True, slots=True)
class JobContext:
    """Ce que le gestionnaire sait de son exécution (jamais l'objet requête)."""

    job_id: int
    kind: str
    attempt: int
    max_attempts: int
    worker: str
    fast_path: bool = False


type Handler = Callable[[dict[str, Any], JobContext], None]
type FailureHook = Callable[[dict[str, Any]], None]


@dataclass(frozen=True, slots=True)
class JobType:
    kind: str
    handler: Handler
    on_final_failure: FailureHook | None = None


_registry: dict[str, JobType] = {}


def register_job(
    kind: str, *, on_final_failure: FailureHook | None = None
) -> Callable[[Handler], Handler]:
    """Décorateur : enregistre le gestionnaire du type ``kind`` (``app.verbe``).

    ``on_final_failure(payload)`` est appelé quand la tâche passe en échec définitif
    (par exemple pour marquer l'e-mail correspondant en échec).
    """
    if len(kind) > KIND_MAX_LENGTH or not KIND_PATTERN.match(kind):
        raise ValueError(f"Type de tâche invalide : {kind!r} (forme « app.verbe »).")

    def decorator(handler: Handler) -> Handler:
        existing = _registry.get(kind)
        if existing is not None and existing.handler is not handler:
            raise ValueError(f"Type de tâche déjà enregistré : {kind}")
        _registry[kind] = JobType(kind=kind, handler=handler, on_final_failure=on_final_failure)
        return handler

    return decorator


def unregister_job(kind: str) -> None:
    """Retire un type du registre (tests)."""
    _registry.pop(kind, None)


def registered_kinds() -> frozenset[str]:
    return frozenset(_registry)


def worker_id() -> str:
    """Identifiant de l'exécutant : ``hôte:pid``."""
    return f"{socket.gethostname()}:{os.getpid()}"[:WORKER_MAX_LENGTH]


def safe_error_text(exc: BaseException) -> str:
    """Message d'erreur conservable : type et message, adresses masquées, 2 000 caractères."""
    text = f"{type(exc).__name__}: {exc}"
    text = _EMAIL_IN_TEXT.sub(lambda match: mask_email(match.group(0)), text)
    return text[:LAST_ERROR_MAX_LENGTH]


def retry_delay(attempts: int) -> timedelta:
    """Délai avant la tentative suivante, après ``attempts`` échecs (``attempts`` ≥ 1)."""
    return RETRY_DELAYS[min(max(attempts, 1), len(RETRY_DELAYS)) - 1]


def _validate_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("Les données d'une tâche forment un dictionnaire.")
    scalars = (str, int, float, bool, type(None))
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("Les clés des données d'une tâche sont des chaînes.")
        if any(part in key.lower() for part in FORBIDDEN_PAYLOAD_KEY_PARTS):
            raise ValueError(f"Clé interdite dans les données d'une tâche : {key!r}")
        items = value if isinstance(value, list | tuple) else [value]
        if not all(isinstance(item, scalars) for item in items):
            raise TypeError(f"Données de tâche : identifiants et scalaires seulement ({key!r}).")
    if contains_clear_email(payload):
        raise ValueError("Données de tâche : aucune adresse e-mail (passer un identifiant).")
    return {
        key: list(value) if isinstance(value, tuple) else value for key, value in payload.items()
    }


def enqueue(
    kind: str,
    payload: Mapping[str, Any] | None = None,
    *,
    run_at: datetime | None = None,
    priority: int = Job.PRIORITY_DEFAULT,
    dedup_key: str | None = None,
    max_attempts: int = Job.DEFAULT_MAX_ATTEMPTS,
) -> Job:
    """Crée une tâche dans la transaction de l'appelant ; idempotent par ``dedup_key``.

    Avec ``dedup_key``, une tâche existante portant la même clé est renvoyée telle quelle
    (quel que soit son statut) : la même tâche n'est jamais programmée deux fois.
    """
    if kind not in _registry:
        raise ValueError(f"Type de tâche inconnu : {kind!r} (register_job).")
    if max_attempts < 1:
        raise ValueError("max_attempts doit valoir au moins 1.")
    if not 0 <= priority <= 32767:
        raise ValueError("Priorité hors bornes.")
    fields = {
        "kind": kind,
        "payload": _validate_payload(payload or {}),
        "run_at": run_at or timezone.now(),
        "priority": priority,
        "max_attempts": max_attempts,
    }
    if dedup_key is None:
        return Job.objects.create(**fields)
    if not dedup_key or len(dedup_key) > DEDUP_KEY_MAX_LENGTH or contains_clear_email(dedup_key):
        raise ValueError("Clé de déduplication invalide (non vide, 128 caractères, sans adresse).")

    existing = Job.objects.filter(dedup_key=dedup_key).first()
    if existing is None:
        try:
            # Point de sauvegarde : un doublon concurrent n'annule pas la transaction appelante.
            with transaction.atomic():
                return Job.objects.create(dedup_key=dedup_key, **fields)
        except IntegrityError:
            existing = Job.objects.get(dedup_key=dedup_key)
    if existing.kind != kind:
        raise ValueError(f"Clé de déduplication déjà utilisée par un autre type : {dedup_key}")
    return existing


def _final_failure(job: Job, error_type: str) -> None:
    """Échec définitif : crochet du type de tâche, puis alerte aux opérateurs."""
    job_type = _registry.get(job.kind)
    if job_type is not None and job_type.on_final_failure is not None:
        try:
            job_type.on_final_failure(dict(job.payload))
        except Exception:
            logger.exception("Crochet d'échec définitif en erreur (tâche %s).", job.pk)
    logger.error("Tâche %s (%s) en échec définitif : %s", job.pk, job.kind, error_type)
    send_operator_alert(
        _("Tâche en échec définitif"),
        [
            (_("Tâche"), f"#{job.pk}"),
            (_("Type"), job.kind),
            (_("Tentatives"), str(job.attempts)),
            (_("Erreur"), error_type),
        ],
    )


def _mine(job_id: int, worker: str):
    """Tâche encore réservée par ``worker`` (garde de toute mise à jour après exécution)."""
    return Job.objects.filter(pk=job_id, status=JobStatus.RUNNING, locked_by=worker)


def run_job(job_id: int, *, worker: str, fast_path: bool = False) -> JobOutcome | None:
    """Réserve puis exécute une tâche ; ``None`` si elle n'est pas (ou plus) disponible."""
    now = timezone.now()
    reserved = Job.objects.filter(pk=job_id, status=JobStatus.PENDING, run_at__lte=now).update(
        status=JobStatus.RUNNING,
        locked_at=now,
        locked_by=worker,
        attempts=F("attempts") + 1,
        updated_at=now,
    )
    if reserved != 1:
        return None
    job = Job.objects.get(pk=job_id)
    job_type = _registry.get(job.kind)
    context = JobContext(
        job_id=job.pk,
        kind=job.kind,
        attempt=job.attempts,
        max_attempts=job.max_attempts,
        worker=worker,
        fast_path=fast_path,
    )
    try:
        if job_type is None:
            raise LookupError(f"Type de tâche non enregistré : {job.kind}")
        job_type.handler(dict(job.payload), context)
    except JobDeferred as deferral:
        _mine(job.pk, worker).update(
            status=JobStatus.PENDING,
            run_at=deferral.run_at,
            attempts=F("attempts") - 1,
            locked_at=None,
            locked_by="",
            updated_at=timezone.now(),
        )
        return JobOutcome.DEFERRED
    except Exception as exc:
        logger.warning(
            "Tâche %s (%s), tentative %s/%s en échec.",
            job.pk,
            job.kind,
            job.attempts,
            job.max_attempts,
            exc_info=True,
        )
        return _record_failure(job, worker, exc, permanent=job_type is None)
    _mine(job.pk, worker).update(
        status=JobStatus.SUCCEEDED, finished_at=timezone.now(), updated_at=timezone.now()
    )
    return JobOutcome.SUCCEEDED


def _record_failure(job: Job, worker: str, exc: Exception, *, permanent: bool) -> JobOutcome:
    now = timezone.now()
    error = safe_error_text(exc)
    if permanent or job.attempts >= job.max_attempts:
        updated = _mine(job.pk, worker).update(
            status=JobStatus.FAILED, finished_at=now, last_error=error, updated_at=now
        )
        if updated:
            _final_failure(job, type(exc).__name__)
        return JobOutcome.FAILED
    _mine(job.pk, worker).update(
        status=JobStatus.PENDING,
        run_at=now + retry_delay(job.attempts),
        last_error=error,
        locked_at=None,
        locked_by="",
        updated_at=now,
    )
    return JobOutcome.RETRY


def recover_stale_jobs(*, now: datetime | None = None) -> dict[str, int]:
    """Tâches ``running`` dont le bail a expiré : remises en file, ou en échec si épuisées."""
    now = now or timezone.now()
    stale = Job.objects.filter(status=JobStatus.RUNNING, locked_at__lt=now - JOB_LEASE)
    message = _("Bail expiré : exécution interrompue.")
    exhausted = list(stale.filter(attempts__gte=F("max_attempts")))
    failed = 0
    for job in exhausted:
        if (
            stale.filter(pk=job.pk).update(
                status=JobStatus.FAILED, finished_at=now, last_error=message, updated_at=now
            )
            == 1
        ):
            failed += 1
            _final_failure(job, "LeaseExpired")
    requeued = stale.filter(attempts__lt=F("max_attempts")).update(
        status=JobStatus.PENDING,
        run_at=now,
        locked_at=None,
        locked_by="",
        last_error=message,
        updated_at=now,
    )
    if requeued or failed:
        logger.warning("Tâches au bail expiré : %s remises en file, %s en échec.", requeued, failed)
    return {"requeued": requeued, "failed": failed}


def process_jobs(
    *,
    max_seconds: float,
    worker: str,
    batch_size: int = BATCH_SIZE,
    clock: Callable[[], float] = time.monotonic,
) -> int:
    """Exécute les tâches éligibles par lots, sans commencer de tâche après ``max_seconds``.

    Sélection triée par priorité, échéance puis identifiant. Renvoie le nombre de tâches
    exécutées (réservées par cet exécutant), quel qu'en soit le résultat.
    """
    deadline = clock() + max_seconds
    processed = 0
    attempted: set[int] = set()
    while clock() < deadline:
        candidates = list(
            Job.objects.filter(status=JobStatus.PENDING, run_at__lte=timezone.now())
            .order_by("priority", "run_at", "id")
            .values_list("id", flat=True)[:batch_size]
        )
        batch = [job_id for job_id in candidates if job_id not in attempted]
        if not batch:
            break
        for job_id in batch:
            if clock() >= deadline:
                break
            attempted.add(job_id)
            if run_job(job_id, worker=worker) is not None:
                processed += 1
    return processed
