"""Données personnelles de l'organisation (registre ``apps.core.personal_data``, RG-18 ;
plan L8, N15).

- **Tâches** (N3) : export des tâches confiées à la personne ou créées par elle, de ses
  commentaires (texte compris) et des pièces jointes qu'elle a déposées (nom, type, taille).
  À l'anonymisation, rien n'est effacé : ce sont des documents de travail du comité, gardés
  avec leur auteur, dont le compte anonymisé n'affiche plus de nom.
- **Budget** (N4) : aucune donnée personnelle (aucune clé vers un compte).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.personal_data import register_personal_data
from apps.logistics.models import Task, TaskAttachment, TaskComment


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    return {
        "tasks": [
            {
                "edition": row.edition.code,
                "title": row.title,
                "status": row.status,
                "due_date": _iso(row.due_date),
                "assigned_to_me": row.assignee_id == user.pk,
                "created_by_me": row.created_by_id == user.pk,
            }
            for row in Task.objects.filter(Q(assignee=user) | Q(created_by=user))
            .select_related("edition")
            .order_by("edition_id", "id")
        ],
        "task_comments": [
            {"edition": row.task.edition.code, "task": row.task.title, "body": row.body}
            for row in TaskComment.objects.filter(author=user)
            .select_related("task__edition")
            .order_by("created_at", "id")
        ],
        "task_attachments": [
            {
                "edition": row.task.edition.code,
                "task": row.task.title,
                "name": row.name,
                "kind": row.kind,
                "size": row.size,
            }
            for row in TaskAttachment.objects.filter(uploaded_by=user)
            .select_related("task__edition")
            .order_by("created_at", "id")
        ],
    }


def register_logistics_personal_data() -> None:
    register_personal_data(
        "logistics.tasks",
        models=("logistics.Task", "logistics.TaskComment", "logistics.TaskAttachment"),
        export=_export,
        anonymize=None,
        rank=500,
    )
