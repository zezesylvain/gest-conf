"""Rappels de la confirmation de présentation (plan L5, §9 ; retenu à la validation du plan).

Tant que l'auteur n'a pas confirmé (statut ``CAMERA_READY_RECEIVED``), le soumissionnaire
reçoit un rappel trois jours, puis dix jours après la réception de sa version finale (date
lue dans l'historique des statuts), une fois chacun. Un passage manqué n'est pas rattrapé :
seul le rappel le plus récent part. Commande ``remind_presentations``, lancée toutes les
heures par le cron : idempotente (clé d'idempotence de l'e-mail) et verrouillée (règle n° 9).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from apps.communications.models import OutboxEmail
from apps.conferences.models import EditionStatus
from apps.submissions.models import StatusHistory, Submission
from apps.submissions.models import SubmissionStatus as S

# Du plus tardif au plus précoce : le premier atteint est le seul dû.
STAGES: tuple[tuple[str, timedelta], ...] = (
    ("d10", timedelta(days=10)),
    ("d3", timedelta(days=3)),
)


def due_stage(received_at: datetime, now: datetime) -> str | None:
    """Rappel dû à ``now`` pour une version finale reçue à ``received_at``."""
    for code, delay in STAGES:
        if now >= received_at + delay:
            return code
    return None


def reminder_key(submission: Submission, stage: str) -> str:
    return f"program-presentation-reminder:{submission.pk}:{stage}"


def remind_presentations(*, now: datetime | None = None) -> int:
    """Envoie les rappels dus ; renvoie leur nombre."""
    from apps.program.notifications import presentation_reminder

    now = now or timezone.now()
    received = (
        StatusHistory.objects.filter(submission=OuterRef("pk"), to_status=S.CAMERA_READY_RECEIVED)
        .order_by("-at")
        .values("at")[:1]
    )
    pending = (
        Submission.objects.filter(status=S.CAMERA_READY_RECEIVED)
        .exclude(edition__status=EditionStatus.ARCHIVED)
        .annotate(received_at=Subquery(received))
        .filter(received_at__lte=now - STAGES[-1][1])
        .select_related("edition", "submitter")
        .order_by("pk")
    )
    sent = 0
    for submission in pending:
        stage = due_stage(submission.received_at, now)
        if (
            stage is None
            or OutboxEmail.objects.filter(idempotency_key=reminder_key(submission, stage)).exists()
        ):
            continue
        with transaction.atomic():
            presentation_reminder(submission, reminder_key(submission, stage))
        sent += 1
    return sent
