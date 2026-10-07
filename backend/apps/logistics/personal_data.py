"""Données personnelles de l'organisation (registre ``apps.core.personal_data``, RG-18 ;
plan L8, N15).

- **Tâches** (N3) : export des tâches confiées à la personne ou créées par elle, de ses
  commentaires (texte compris) et des pièces jointes qu'elle a déposées (nom, type, taille).
  À l'anonymisation, rien n'est effacé : ce sont des documents de travail du comité, gardés
  avec leur auteur, dont le compte anonymisé n'affiche plus de nom.
- **Budget** (N4) : aucune donnée personnelle (aucune clé vers un compte).
- **Fiche de venue** (N6) et **régime alimentaire** (N7, RG-23) : export complet (note
  interne du CO exclue) ; à l'anonymisation, **effacés**.
- **Affectations de bénévolat** (N9) : export ; gardées à l'anonymisation (le compte
  anonymisé n'affiche plus de nom).
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q

from apps.core.personal_data import AnonymizationContext, register_personal_data
from apps.logistics.models import (
    DietaryDeclaration,
    ShiftAssignment,
    SpeakerVisit,
    Task,
    TaskAttachment,
    TaskComment,
)


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
        "speaker_visits": [
            {
                "edition": row.edition.code,
                **{
                    name: _iso(value) if hasattr(value, "isoformat") else value
                    for name in (*SpeakerVisit.SPEAKER_FIELDS, "hotel", "check_in", "check_out")
                    for value in (getattr(row, name),)
                },
                "status": row.status,
            }
            for row in SpeakerVisit.objects.filter(user=user).select_related("edition")
        ],
        "dietary_declarations": [
            {
                "edition": row.edition.code,
                "diets": row.diets,
                "allergies": row.allergies,
                "consented_at": _iso(row.consented_at),
            }
            for row in DietaryDeclaration.objects.filter(user=user).select_related("edition")
        ],
        "volunteer_shifts": [
            {
                "edition": row.shift.edition.code,
                "title": row.shift.title_fr,
                "starts_at": _iso(row.shift.starts_at),
                "ends_at": _iso(row.shift.ends_at),
            }
            for row in ShiftAssignment.objects.filter(volunteer=user)
            .select_related("shift__edition")
            .order_by("shift__starts_at")
        ],
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    SpeakerVisit.objects.filter(user=user).delete()
    DietaryDeclaration.objects.filter(user=user).delete()


def register_logistics_personal_data() -> None:
    register_personal_data(
        "logistics.tasks",
        models=(
            "logistics.Task",
            "logistics.TaskComment",
            "logistics.TaskAttachment",
            "logistics.SpeakerVisit",
            "logistics.DietaryDeclaration",
            "logistics.ShiftAssignment",
        ),
        export=_export,
        anonymize=_anonymize,
        rank=500,
    )
