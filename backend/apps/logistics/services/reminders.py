"""Récapitulatif quotidien des tâches (plan L8, N3).

Chaque responsable reçoit, une fois par jour et par édition, la liste de ses tâches ni
terminées ni archivées dont l'échéance est passée ou tombe dans les deux jours (date du jour
dans le fuseau de l'édition). Commande ``remind_tasks`` : idempotente (date du dernier
récapitulatif sur chaque tâche, clé d'idempotence de l'e-mail) et verrouillée (règle n° 9).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.conferences.models import EditionStatus
from apps.logistics.models import Task, TaskStatus

HORIZON = timedelta(days=2)


def remind_tasks(*, now: datetime | None = None) -> int:
    """Envoie les récapitulatifs dus ; renvoie leur nombre."""
    from apps.logistics.notifications import tasks_reminder

    now = now or timezone.now()
    candidates = (
        Task.objects.filter(
            archived_at__isnull=True,
            due_date__isnull=False,
            assignee__isnull=False,
            assignee__is_active=True,
            assignee__anonymized_at__isnull=True,
            due_date__lte=(now + HORIZON + timedelta(days=1)).date(),
        )
        .exclude(status=TaskStatus.DONE)
        .exclude(edition__status=EditionStatus.ARCHIVED)
        .select_related("edition", "assignee")
        .order_by("edition_id", "assignee_id", "due_date", "id")
    )
    groups: dict[tuple[int, int], list[Task]] = defaultdict(list)
    for task in candidates:
        groups[(task.edition_id, task.assignee_id)].append(task)
    sent = 0
    for tasks in groups.values():
        edition, user = tasks[0].edition, tasks[0].assignee
        today = now.astimezone(ZoneInfo(edition.timezone)).date()
        due = [
            task
            for task in tasks
            if task.due_date <= today + HORIZON
            and (task.reminded_on is None or task.reminded_on < today)
        ]
        if not due:
            continue
        with transaction.atomic():
            tasks_reminder(
                edition,
                user,
                due,
                today=today,
                idempotency_key=f"tasks-reminder:{edition.pk}:{user.pk}:{today.isoformat()}",
            )
            Task.objects.filter(pk__in=[task.pk for task in due]).update(reminded_on=today)
        sent += 1
    return sent
