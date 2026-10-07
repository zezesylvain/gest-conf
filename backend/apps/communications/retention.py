"""Règles de conservation du registre d'envoi (D15, plan L1 §3.6 et §8.4).

- Sécurité, toujours appliquée, à chaque passage de ``run_jobs`` et par ``cleanup`` :
  corps des e-mails sensibles (liens à jeton) d'un e-mail envoyé dont la purge aurait été
  interrompue, et de tout e-mail sensible non envoyé depuis 24 h, alors annulé avec sa
  tâche. Sinon, un simple accès en lecture à la base suffirait pour réinitialiser des
  mots de passe ou accepter des invitations.
- Cadre légal, en simulation par défaut : autres corps après 30 jours, lignes du registre
  (métadonnées d'envoi) après 12 mois.
"""

from __future__ import annotations

from datetime import datetime

from django.db import transaction
from django.db.models import Q, QuerySet

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import SEND_EMAIL_JOB
from apps.core.actor import Actor
from apps.core.models import Job, JobStatus
from apps.core.retention import (
    EMAIL_BODY_RETENTION,
    EMAIL_METADATA_RETENTION,
    SENSITIVE_EMAIL_BODY_MAX_AGE,
    RetentionCategory,
    RetentionRule,
    register_rule,
)

TERMINAL_STATUSES = (OutboxStatus.SENT, OutboxStatus.FAILED, OutboxStatus.CANCELLED)
UNSENT_STATUSES = (OutboxStatus.QUEUED, OutboxStatus.SENDING, OutboxStatus.FAILED)


def _with_body() -> Q:
    return ~Q(body_text="") | ~Q(body_html="")


def _sensitive_bodies(now: datetime) -> QuerySet[OutboxEmail]:
    """Corps sensibles à purger : envoyés (purge interrompue) ou non envoyés depuis 24 h."""
    return OutboxEmail.objects.filter(is_sensitive=True, purged_at__isnull=True).filter(
        Q(status=OutboxStatus.SENT)
        | Q(status__in=UNSENT_STATUSES, created_at__lt=now - SENSITIVE_EMAIL_BODY_MAX_AGE)
        | Q(status=OutboxStatus.CANCELLED)
    )


def purge_sensitive_bodies(now: datetime, actor: Actor) -> int:
    with transaction.atomic():
        targets = list(_sensitive_bodies(now).values_list("pk", "status"))
        unsent = [pk for pk, status in targets if status in UNSENT_STATUSES]
        OutboxEmail.objects.filter(pk__in=[pk for pk, _ in targets]).update(
            body_text="", body_html="", purged_at=now, updated_at=now
        )
        # Lien perdu : l'e-mail non envoyé est annulé, ainsi que sa tâche en attente.
        OutboxEmail.objects.filter(pk__in=unsent).exclude(status=OutboxStatus.SENDING).update(
            status=OutboxStatus.CANCELLED, updated_at=now
        )
        Job.objects.filter(
            kind=SEND_EMAIL_JOB,
            status=JobStatus.PENDING,
            dedup_key__in=[f"email:{pk}" for pk in unsent],
        ).update(status=JobStatus.CANCELLED, finished_at=now, updated_at=now)
    return len(targets)


register_rule(
    RetentionRule(
        name="communications.sensitive_bodies",
        category=RetentionCategory.SECURITY,
        count=lambda now: _sensitive_bodies(now).count(),
        apply=purge_sensitive_bodies,
        with_jobs=True,
    )
)


def _old_bodies(now: datetime) -> QuerySet[OutboxEmail]:
    return OutboxEmail.objects.filter(
        status__in=TERMINAL_STATUSES, created_at__lt=now - EMAIL_BODY_RETENTION
    ).filter(_with_body())


def purge_old_bodies(now: datetime, actor: Actor) -> int:
    return _old_bodies(now).update(body_text="", body_html="", purged_at=now, updated_at=now)


register_rule(
    RetentionRule(
        name="communications.email_bodies",
        category=RetentionCategory.LEGAL,
        count=lambda now: _old_bodies(now).count(),
        apply=purge_old_bodies,
    )
)


def _old_metadata(now: datetime) -> QuerySet[OutboxEmail]:
    return OutboxEmail.objects.filter(
        status__in=TERMINAL_STATUSES, created_at__lt=now - EMAIL_METADATA_RETENTION
    )


def delete_old_metadata(now: datetime, actor: Actor) -> int:
    with transaction.atomic():
        return _old_metadata(now).delete()[0]


register_rule(
    RetentionRule(
        name="communications.email_metadata",
        category=RetentionCategory.LEGAL,
        count=lambda now: _old_metadata(now).count(),
        apply=delete_old_metadata,
    )
)
