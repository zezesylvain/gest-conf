"""Tâches du comité d'organisation (plan L8, N3 ; étude M11).

Seul module qui écrit les tâches :

- chaque écriture verrouille la tâche, compare la révision lue (``If-Match`` ; 412
  ``stale_revision`` si elle a changé), l'incrémente et écrit le journal ``task.*`` ;
- le responsable est un membre actif de l'édition qui détient ``tasks.write`` (rôles tirés
  de la table des capacités, jamais recopiés) ;
- l'ordre d'une colonne du kanban est renuméroté à chaque déplacement (0, 1, 2…) ;
- une tâche n'est jamais supprimée : archivée, puis éventuellement restaurée ;
- pièces jointes : PDF, PNG ou JPEG de 10 Mo au plus, type vérifié par contenu, stockées
  hors racine web (règle n° 8).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import CAPABILITIES, Capability
from apps.accounts.services.roles import ensure_editable
from apps.communications.models import NotificationKind
from apps.communications.notifications import notify
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid, StaleRevision
from apps.core.private_files import PrivateStore, sniff
from apps.logistics.models import Task, TaskAttachment, TaskComment, TaskPriority, TaskStatus

ATTACHMENTS = PrivateStore("task-attachments")
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
ATTACHMENTS_PER_TASK = 20
DESCRIPTION_MAX_LENGTH = 5000
COMMENT_MAX_LENGTH = 2000
# Rôles qui partagent les tâches : ceux dont la table des capacités donne ``tasks.write``.
TASK_ROLES = frozenset(
    role for role, capabilities in CAPABILITIES.items() if Capability.TASKS_WRITE in capabilities
)
WRITABLE_FIELDS = frozenset(
    {"title", "description", "status", "priority", "label", "assignee", "due_date", "position"}
)


def task_members(edition: Edition):
    """Comptes à qui confier une tâche : membres actifs de l'édition avec ``tasks.write``."""
    holders = UserRole.objects.filter(
        edition=edition, status=UserRoleStatus.ACTIVE, role__in=TASK_ROLES
    ).values("user_id")
    return User.objects.filter(pk__in=holders, is_active=True, anonymized_at__isnull=True)


def _assignee(edition: Edition, value: Any) -> User | None:
    if value in (None, ""):
        return None
    user_id = value.pk if isinstance(value, User) else value
    user = task_members(edition).filter(pk=user_id).first()
    if user is None:
        raise Invalid(fields={"assignee": [_("Membre du comité d'organisation attendu.")]})
    return user


def _clean(edition: Edition, data: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    unknown = set(data) - WRITABLE_FIELDS
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    clean: dict[str, Any] = {}
    errors: dict[str, list] = {}
    if "title" in data or creating:
        title = (data.get("title") or "").strip()
        if not title:
            errors["title"] = [_("Titre obligatoire.")]
        elif len(title) > 200:
            errors["title"] = [_("200 caractères au plus.")]
        clean["title"] = title
    if "description" in data:
        description = (data["description"] or "").strip()
        if len(description) > DESCRIPTION_MAX_LENGTH:
            errors["description"] = [_("5 000 caractères au plus.")]
        clean["description"] = description
    if "label" in data:
        label = (data["label"] or "").strip()
        if len(label) > 50:
            errors["label"] = [_("50 caractères au plus.")]
        clean["label"] = label
    if "status" in data:
        if data["status"] not in TaskStatus.values:
            errors["status"] = [_("Statut inconnu.")]
        clean["status"] = data["status"]
    if "priority" in data:
        if data["priority"] not in TaskPriority.values:
            errors["priority"] = [_("Priorité inconnue.")]
        clean["priority"] = data["priority"]
    if "due_date" in data:
        due = data["due_date"]
        if due is not None and not isinstance(due, dt.date):
            errors["due_date"] = [_("Date attendue.")]
        clean["due_date"] = due
    if "position" in data:
        position = data["position"]
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            errors["position"] = [_("Position positive ou nulle attendue.")]
        clean["position"] = position
    if errors:
        raise Invalid(fields=errors)
    if "assignee" in data:
        clean["assignee"] = _assignee(edition, data["assignee"])
    return clean


def _snapshot(task: Task) -> dict[str, Any]:
    values = {name: getattr(task, name) for name in Task.AUDIT_FIELDS if name != "assignee"}
    values["assignee"] = task.assignee_id
    if values.get("due_date"):
        values["due_date"] = values["due_date"].isoformat()
    return values


def _column(edition: Edition, status: str, *, excluding: int | None = None):
    rows = Task.objects.select_for_update().filter(
        edition=edition, status=status, archived_at__isnull=True
    )
    if excluding is not None:
        rows = rows.exclude(pk=excluding)
    return list(rows.order_by("position", "id"))


def _place(task: Task, position: int | None) -> None:
    """Insère ``task`` à ``position`` dans sa colonne (à la fin si ``None``) et renumérote
    la colonne ; la tâche est enregistrée par l'appelant."""
    others = _column(task.edition, task.status, excluding=task.pk)
    index = len(others) if position is None else min(position, len(others))
    others.insert(index, task)
    for rank, row in enumerate(others):
        if row.pk == task.pk:
            task.position = rank
        elif row.position != rank:
            Task.objects.filter(pk=row.pk).update(position=rank)


def _notify_assignee(task: Task, actor: Actor) -> None:
    if task.assignee is None or (actor.user is not None and actor.user.pk == task.assignee_id):
        return
    notify(
        task.assignee,
        NotificationKind.TASK_ASSIGNED,
        {
            "edition_id": task.edition_id,
            "edition_code": task.edition.code,
            "task_id": task.pk,
            "title": task.title,
        },
    )


@transaction.atomic
def create_task(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Task:
    ensure_editable(edition)
    clean = _clean(edition, data, creating=True)
    position = clean.pop("position", None)
    task = Task(edition=edition, created_by=actor.user, **clean)
    if task.status == TaskStatus.DONE:
        task.done_at = timezone.now()
    task.save()
    _place(task, position)
    task.save(update_fields=["position"])
    record("task.created", actor=actor, edition=edition, obj=task, after=_snapshot(task))
    _notify_assignee(task, actor)
    return task


def _locked(task: Task, revision: int | None) -> Task:
    locked = Task.objects.select_for_update().select_related("edition").get(pk=task.pk)
    if revision is not None and revision != locked.revision:
        raise StaleRevision()
    return locked


@transaction.atomic
def update_task(
    task: Task, data: Mapping[str, Any], *, actor: Actor, revision: int | None = None
) -> Task:
    """Modifie une tâche ; ``status`` et ``position`` la déplacent dans le kanban."""
    ensure_editable(task.edition)
    task = _locked(task, revision)
    if task.archived_at is not None:
        raise Invalid(fields={"task": [_("Tâche archivée : restaurez-la d'abord.")]})
    clean = _clean(task.edition, data, creating=False)
    before = _snapshot(task)
    previous_assignee = task.assignee_id
    previous_status = task.status
    moving = "status" in clean or "position" in clean
    position = clean.pop("position", None)
    for name, value in clean.items():
        setattr(task, name, value)
    if task.status != previous_status:
        task.done_at = timezone.now() if task.status == TaskStatus.DONE else None
    if moving:
        if previous_status != task.status:
            # La colonne quittée se resserre.
            for rank, row in enumerate(_column(task.edition, previous_status, excluding=task.pk)):
                if row.position != rank:
                    Task.objects.filter(pk=row.pk).update(position=rank)
        _place(task, position)
    task.revision += 1
    task.save()
    after = _snapshot(task)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "task.updated",
            actor=actor,
            edition=task.edition,
            obj=task,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    if task.assignee_id != previous_assignee:
        _notify_assignee(task, actor)
    return task


@transaction.atomic
def archive_task(task: Task, *, actor: Actor, revision: int | None = None) -> Task:
    ensure_editable(task.edition)
    task = _locked(task, revision)
    if task.archived_at is None:
        task.archived_at = timezone.now()
        task.revision += 1
        task.save(update_fields=["archived_at", "revision", "updated_at"])
        for rank, row in enumerate(_column(task.edition, task.status)):
            if row.position != rank:
                Task.objects.filter(pk=row.pk).update(position=rank)
        record("task.archived", actor=actor, edition=task.edition, obj=task)
    return task


@transaction.atomic
def restore_task(task: Task, *, actor: Actor, revision: int | None = None) -> Task:
    ensure_editable(task.edition)
    task = _locked(task, revision)
    if task.archived_at is not None:
        task.archived_at = None
        _place(task, None)
        task.revision += 1
        task.save(update_fields=["archived_at", "position", "revision", "updated_at"])
        record("task.restored", actor=actor, edition=task.edition, obj=task)
    return task


@transaction.atomic
def add_comment(task: Task, body: str, *, actor: Actor) -> TaskComment:
    ensure_editable(task.edition)
    text = (body or "").strip()
    if not text:
        raise Invalid(fields={"body": [_("Commentaire vide.")]})
    if len(text) > COMMENT_MAX_LENGTH:
        raise Invalid(fields={"body": [_("2 000 caractères au plus.")]})
    comment = TaskComment.objects.create(task=task, author=actor.user, body=text)
    # Le journal ne garde pas le texte (contenu de travail, pas une action sensible).
    record("task.commented", actor=actor, edition=task.edition, obj=task)
    return comment


@transaction.atomic
def add_attachment(task: Task, *, data: bytes, name: str, actor: Actor) -> TaskAttachment:
    ensure_editable(task.edition)
    task = Task.objects.select_for_update().select_related("edition").get(pk=task.pk)
    if task.attachments.count() >= ATTACHMENTS_PER_TASK:
        raise Invalid(fields={"file": [_("20 pièces jointes au plus par tâche.")]})
    if len(data) > ATTACHMENT_MAX_BYTES:
        raise Invalid(fields={"file": [_("Fichier de 10 Mo au plus.")]})
    kind = sniff(data)
    if kind is None:
        raise Invalid(fields={"file": [_("PDF, JPEG ou PNG attendu.")]})
    storage_name, digest = ATTACHMENTS.write(data)
    attachment = TaskAttachment.objects.create(
        task=task,
        storage_name=storage_name,
        name=(name or "piece-jointe").replace("/", "_").replace("\\", "_")[:255],
        kind=kind,
        size=len(data),
        sha256=digest,
        uploaded_by=actor.user,
    )
    record(
        "task.attachment_added",
        actor=actor,
        edition=task.edition,
        obj=task,
        after={"name": attachment.name, "kind": kind, "size": len(data)},
    )
    return attachment


@transaction.atomic
def remove_attachment(attachment: TaskAttachment, *, actor: Actor) -> None:
    task = attachment.task
    ensure_editable(task.edition)
    ATTACHMENTS.remove_after_commit(attachment.storage_name)
    record(
        "task.attachment_removed",
        actor=actor,
        edition=task.edition,
        obj=task,
        before={"name": attachment.name, "kind": attachment.kind, "size": attachment.size},
    )
    attachment.delete()


def known_attachments() -> list[str]:
    return list(TaskAttachment.objects.values_list("storage_name", flat=True))
