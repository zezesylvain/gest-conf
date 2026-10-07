"""Fil d'activité du CO (plan L8, N14) : les 50 dernières entrées du journal de l'édition,
restreintes à une **liste blanche** d'actions non sensibles. Ni décision, ni identité
d'auteur, ni montant individuel ; jamais les valeurs avant et après d'une entrée, seulement
l'action, sa date, qui l'a faite et l'objet visé."""

from __future__ import annotations

from typing import Any

from apps.conferences.models import Edition
from apps.core.models import AuditLog

LIMIT = 50
ACTIONS = frozenset(
    {
        "task.created",
        "task.updated",
        "task.commented",
        "task.archived",
        "task.restored",
        "task.attachment_added",
        "task.attachment_removed",
        "shift.created",
        "shift.updated",
        "shift.deleted",
        "shift.assigned",
        "shift.unassigned",
        "meal.created",
        "meal.updated",
        "meal.deleted",
        "announcement.published",
        "announcement.withdrawn",
        "survey.published",
        "program.published",
        "portal.published",
        "edition.status_changed",
    }
)


def feed(edition: Edition) -> list[dict[str, Any]]:
    from apps.accounts.services.invitations import display_name

    rows = (
        AuditLog.objects.filter(edition=edition, action__in=ACTIONS)
        .select_related("actor__profile")
        .order_by("-at", "-id")[:LIMIT]
    )
    return [
        {
            "at": row.at,
            "action": row.action,
            "actor": display_name(row.actor) if row.actor_id else "",
            "object_type": row.object_type,
            "object_id": row.object_id,
        }
        for row in rows
    ]
