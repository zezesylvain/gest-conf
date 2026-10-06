"""Relances des relecteurs (plan L4, H15) : sept jours et un jour avant l'échéance, puis au
premier passage après elle, **une fois chacune** (codes notés dans ``reminders`` de
l'affectation, sous verrou). Commande ``remind_reviewers``, lancée par le cron toutes les
heures : idempotente et verrouillée (règle n° 9)."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from apps.conferences.models import EditionStatus
from apps.reviews.models import AssignmentStatus, ReviewAssignment, ReviewStatus
from apps.reviews.services.assignments import NOTIFIED

LATE = "late"
# Fenêtres avant l'échéance, de la plus large à la plus étroite.
WINDOWS: tuple[tuple[str, timedelta], ...] = (("j7", timedelta(days=7)), ("j1", timedelta(days=1)))


def due_reminder(assignment: ReviewAssignment, now: datetime) -> str | None:
    """Relance due à ``now`` : ``late`` après l'échéance ; sinon celle de la fenêtre la plus
    étroite qui contient ``now``, sauf si l'affectation y est née (l'e-mail d'affectation
    vient d'annoncer l'échéance). Aucune si elle a déjà été envoyée."""
    due = assignment.due_at
    if due is None:
        return None
    if now >= due:
        kind = LATE
    else:
        kind = None
        for code, window in WINDOWS:
            if due - now <= window and assignment.assigned_at < due - window:
                kind = code
    if kind is None or kind in assignment.reminders:
        return None
    return kind


def remind_reviewers(*, now: datetime | None = None) -> int:
    """Envoie les relances dues ; renvoie leur nombre."""
    from apps.reviews.notifications import reminder

    now = now or timezone.now()
    pending = (
        ReviewAssignment.objects.filter(
            status=AssignmentStatus.ACTIVE,
            due_at__isnull=False,
            due_at__lte=now + WINDOWS[0][1],
            submission__status__in=NOTIFIED,
        )
        .exclude(submission__edition__status=EditionStatus.ARCHIVED)
        .exclude(review__status=ReviewStatus.SUBMITTED)
        .order_by("due_at", "id")
        .values_list("pk", flat=True)
    )
    sent = 0
    for pk in list(pending):
        with transaction.atomic():
            assignment = (
                ReviewAssignment.objects.select_for_update()
                .select_related("submission__edition", "reviewer")
                .get(pk=pk)
            )
            kind = due_reminder(assignment, now)
            if kind is None:
                continue
            assignment.reminders = [*assignment.reminders, kind]
            assignment.save(update_fields=["reminders", "updated_at"])
            reminder(assignment, kind)
            sent += 1
    return sent
