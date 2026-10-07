"""Purges et durées de conservation (décision D15, plan L1 §8.4, arbitrage L1.2).

Chaque application déclare ses règles (``register_rule``) ; la commande ``cleanup`` les
exécute toutes chaque nuit, ``run_jobs`` celles marquées ``with_jobs`` à chaque passage.

Deux catégories :

- **sécurité** (``SECURITY``), toujours appliquées : corps des e-mails sensibles (liens à
  jeton), entrées expirées des deux tables de cache, sessions expirées ;
- **cadre légal** (``LEGAL``), qui dépendent des durées de D15 : **simulées** (simple
  comptage de ce qui serait purgé) tant que ``GESTCONF_RETENTION_ENFORCE`` n'est pas activé,
  car le cadre légal (Q14) n'est pas tranché.

Les durées sont des constantes nommées, regroupées ci-dessous pour être relues d'un coup
d'œil avec le tableau de D15.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from importlib import import_module
from typing import Any

from django.conf import settings
from django.core.cache import caches
from django.core.cache.backends.db import DatabaseCache
from django.db import connections, router, transaction
from django.db.models import Q

from apps.core.actor import Actor
from apps.core.models import AuditLog, Job, JobStatus

logger = logging.getLogger(__name__)

# --- Durées de conservation (D15) ------------------------------------------------------
# Sécurité : corps d'un e-mail sensible non envoyé (lien à jeton), au plus 24 h.
SENSITIVE_EMAIL_BODY_MAX_AGE = timedelta(hours=24)
# Cadre légal (simulation tant que GESTCONF_RETENTION_ENFORCE est faux) :
EMAIL_BODY_RETENTION = timedelta(days=30)  # autres corps d'e-mails
EMAIL_METADATA_RETENTION = timedelta(days=365)  # métadonnées d'envoi : 12 mois
AUDIT_NETWORK_RETENTION = timedelta(days=183)  # IP et user-agent de l'audit : 6 mois
AUDIT_RETENTION = timedelta(days=1096)  # lignes du journal d'audit : 3 ans
FINISHED_JOB_RETENTION = timedelta(days=30)  # tâches terminées

TERMINAL_JOB_STATUSES = (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED)


class RetentionCategory(StrEnum):
    SECURITY = "security"
    LEGAL = "legal"


class RetentionMode(StrEnum):
    APPLIED = "applied"
    SIMULATED = "simulated"


@dataclass(frozen=True, slots=True)
class RetentionRule:
    """Une purge : ``count(now)`` compte ce qu'elle viserait, ``apply(now, actor)`` l'exécute.

    ``apply`` renvoie le nombre d'éléments purgés ; il est idempotent (un second passage
    immédiat ne trouve plus rien).
    """

    name: str
    category: RetentionCategory
    count: Callable[[datetime], int]
    apply: Callable[[datetime, Actor], int]
    with_jobs: bool = False


_rules: dict[str, RetentionRule] = {}


def register_rule(rule: RetentionRule) -> RetentionRule:
    if rule.with_jobs and rule.category != RetentionCategory.SECURITY:
        raise ValueError("Seules les purges de sécurité tournent à chaque passage de run_jobs.")
    existing = _rules.get(rule.name)
    if existing is not None and existing != rule:
        raise ValueError(f"Règle de conservation déjà enregistrée : {rule.name}")
    _rules[rule.name] = rule
    return rule


def registered_rules() -> list[RetentionRule]:
    return [_rules[name] for name in sorted(_rules)]


def run_rules(
    now: datetime, *, actor: Actor, enforce_legal: bool, only_with_jobs: bool = False
) -> dict[str, dict[str, Any]]:
    """Exécute (ou simule) les règles ; une règle en erreur n'empêche pas les suivantes.

    Rapport par règle : ``{"category", "mode", "count"}``, plus ``"error"`` (type de
    l'exception) en cas d'échec. Aucune donnée personnelle : des nombres.
    """
    report: dict[str, dict[str, Any]] = {}
    for rule in registered_rules():
        if only_with_jobs and not rule.with_jobs:
            continue
        applied = rule.category == RetentionCategory.SECURITY or enforce_legal
        entry: dict[str, Any] = {
            "category": rule.category.value,
            "mode": (RetentionMode.APPLIED if applied else RetentionMode.SIMULATED).value,
        }
        try:
            entry["count"] = rule.apply(now, actor) if applied else rule.count(now)
        except Exception as exc:
            logger.exception("Règle de conservation %s en erreur.", rule.name)
            entry.update(count=0, error=type(exc).__name__)
        report[rule.name] = entry
    return report


# --- Tables de cache (sécurité, plan §3.5 et §16 point 4) -------------------------------


def _database_cache_tables() -> list[tuple[str, str]]:
    """(alias, table) des caches en base : les deux tables, noms tirés de ``CACHES``."""
    return [
        (alias, config["LOCATION"])
        for alias, config in settings.CACHES.items()
        if isinstance(caches[alias], DatabaseCache)
    ]


def _run_on_expired_cache_entries(verb: str, now: datetime) -> dict[str, int]:
    """Exécute ``<verb> FROM <table> WHERE expires < now`` sur chaque table de cache.

    Même requête que la purge interne de Django (``DatabaseCache._cull``, privée) : nom
    de table cité (``quote_name``), échéance passée en paramètre, base choisie par le
    routeur comme le fait le cache lui-même.
    """
    results: dict[str, int] = {}
    for alias, table in _database_cache_tables():
        connection = connections[router.db_for_write(caches[alias].cache_model_class)]
        quote = connection.ops.quote_name
        sql = f"{verb} FROM {quote(table)} WHERE {quote('expires')} < %s"
        expires = connection.ops.adapt_datetimefield_value(now.replace(microsecond=0))
        with connection.cursor() as cursor:
            cursor.execute(sql, [expires])
            results[alias] = cursor.fetchone()[0] if verb.startswith("SELECT") else cursor.rowcount
    return results


def count_expired_cache_entries(now: datetime) -> dict[str, int]:
    return _run_on_expired_cache_entries("SELECT COUNT(*)", now)


def purge_expired_cache_entries(now: datetime) -> dict[str, int]:
    """Supprime les entrées expirées de chaque table de cache ; renvoie le nombre par alias.

    Garde les tables petites : au-delà de ``MAX_ENTRIES``, Django supprimerait un tiers
    des clés par ordre alphabétique, compteurs de limitation de débit compris (R18).
    """
    return _run_on_expired_cache_entries("DELETE", now)


register_rule(
    RetentionRule(
        name="core.cache_expired_entries",
        category=RetentionCategory.SECURITY,
        count=lambda now: sum(count_expired_cache_entries(now).values()),
        apply=lambda now, actor: sum(purge_expired_cache_entries(now).values()),
        with_jobs=True,
    )
)


# --- Sessions expirées (sécurité) --------------------------------------------------------


def _session_store() -> Any:
    return import_module(settings.SESSION_ENGINE).SessionStore


def _count_expired_sessions(now: datetime) -> int:
    if settings.SESSION_ENGINE != "django.contrib.sessions.backends.db":
        return 0
    from django.contrib.sessions.models import Session

    return Session.objects.filter(expire_date__lt=now).count()


def _clear_expired_sessions(now: datetime, actor: Actor) -> int:
    """Équivalent de ``manage.py clearsessions`` (même appel : ``SessionStore.clear_expired``)."""
    count = _count_expired_sessions(now)
    _session_store().clear_expired()
    return count


register_rule(
    RetentionRule(
        name="core.sessions_expired",
        category=RetentionCategory.SECURITY,
        count=_count_expired_sessions,
        apply=_clear_expired_sessions,
    )
)


# --- Journal d'audit (cadre légal, méthodes nommées et auditées) -------------------------


def _with_network(queryset: Any) -> Any:
    return queryset.filter(Q(ip__isnull=False) | ~Q(user_agent=""))


register_rule(
    RetentionRule(
        name="core.audit_network_context",
        category=RetentionCategory.LEGAL,
        count=lambda now: _with_network(
            AuditLog.objects.filter(at__lt=now - AUDIT_NETWORK_RETENTION)
        ).count(),
        apply=lambda now, actor: AuditLog.objects.purge_network_before(
            now - AUDIT_NETWORK_RETENTION, actor=actor
        ),
    )
)

register_rule(
    RetentionRule(
        name="core.audit_entries",
        category=RetentionCategory.LEGAL,
        count=lambda now: AuditLog.objects.filter(at__lt=now - AUDIT_RETENTION).count(),
        apply=lambda now, actor: AuditLog.objects.purge_before(now - AUDIT_RETENTION, actor=actor),
    )
)


# --- Tâches terminées (cadre légal) -------------------------------------------------------


def _finished_jobs(now: datetime) -> Any:
    return Job.objects.filter(
        status__in=TERMINAL_JOB_STATUSES, finished_at__lt=now - FINISHED_JOB_RETENTION
    )


def _delete_finished_jobs(now: datetime, actor: Actor) -> int:
    with transaction.atomic():
        return _finished_jobs(now).delete()[0]


register_rule(
    RetentionRule(
        name="core.finished_jobs",
        category=RetentionCategory.LEGAL,
        count=lambda now: _finished_jobs(now).count(),
        apply=_delete_finished_jobs,
    )
)
