"""Tâches du comité d'organisation (plan L8, N3) : service."""

from __future__ import annotations

import datetime as dt

import pytest

from apps.accounts.models import UserRoleStatus
from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import make_member
from apps.communications.models import Notification, NotificationKind
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, RuleViolation, StaleRevision
from apps.core.models import AuditLog
from apps.logistics.models import Task, TaskStatus
from apps.logistics.services import tasks as service

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%%EOF\n"


def as_user(user) -> Actor:
    return Actor(kind=ActorKind.USER, user=user)


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def chair(edition):
    return make_member(edition, Role.CHAIR)


@pytest.fixture
def logistics(edition):
    return make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.LOGISTICS)


def column(edition, status=TaskStatus.TODO) -> list[str]:
    return list(
        Task.objects.filter(edition=edition, status=status, archived_at__isnull=True)
        .order_by("position")
        .values_list("title", flat=True)
    )


def test_n3_task_members_are_the_holders_of_tasks_write(edition, chair, logistics):
    """Responsable : administrateur, Chair ou CO actif de l'édition ; jamais un relecteur, un
    bénévole, un rôle retiré ni un membre d'une autre édition."""
    admin = make_member(edition, Role.ADMIN)
    reviewer = make_member(edition, Role.SC_MEMBER)
    volunteer = make_member(edition, Role.VOLUNTEER)
    revoked = make_member(edition, Role.OC_MEMBER, status=UserRoleStatus.REVOKED)
    stranger = make_member(EditionFactory(), Role.OC_MEMBER)
    assert set(service.task_members(edition)) == {admin, chair, logistics}
    for user in (reviewer, volunteer, revoked, stranger):
        with pytest.raises(Invalid) as error:
            service.create_task(edition, {"title": "x", "assignee": user.pk}, actor=as_user(chair))
        assert "assignee" in error.value.fields


def test_n3_create_task_validates_places_at_end_and_notifies_the_assignee(
    edition, chair, logistics
):
    with pytest.raises(Invalid) as error:
        service.create_task(edition, {"title": "  "}, actor=as_user(chair))
    assert "title" in error.value.fields
    with pytest.raises(Invalid):
        service.create_task(edition, {"title": "x", "owner": 1}, actor=as_user(chair))
    first = service.create_task(edition, {"title": "Salle"}, actor=as_user(chair))
    second = service.create_task(
        edition,
        {"title": "  Traiteur ", "assignee": logistics.pk, "due_date": dt.date(2027, 5, 1)},
        actor=as_user(chair),
    )
    assert (first.position, second.position) == (0, 1)
    assert second.title == "Traiteur" and second.created_by == chair and second.revision == 1
    notification = Notification.objects.get(user=logistics)
    assert notification.kind == NotificationKind.TASK_ASSIGNED
    assert notification.payload == {
        "edition_id": edition.pk,
        "edition_code": edition.code,
        "task_id": second.pk,
        "title": "Traiteur",
    }
    # Se confier une tâche à soi-même : pas de notification.
    service.create_task(edition, {"title": "Moi", "assignee": chair.pk}, actor=as_user(chair))
    assert not Notification.objects.filter(user=chair).exists()
    assert AuditLog.objects.filter(action="task.created", edition=edition).count() == 3


def test_n3_update_checks_the_revision_and_records_the_changes(edition, chair, logistics):
    task = service.create_task(edition, {"title": "Salle"}, actor=as_user(chair))
    task = service.update_task(
        task, {"assignee": logistics.pk, "priority": "high"}, actor=as_user(chair), revision=1
    )
    assert (task.revision, task.priority, task.assignee) == (2, "high", logistics)
    with pytest.raises(StaleRevision):
        service.update_task(task, {"title": "Autre"}, actor=as_user(chair), revision=1)
    entry = AuditLog.objects.filter(action="task.updated").get()
    assert entry.before == {"priority": "normal", "assignee": None}
    assert entry.after == {"priority": "high", "assignee": logistics.pk}
    assert Notification.objects.filter(user=logistics).count() == 1


def test_n3_moving_a_task_renumbers_both_columns_and_tracks_completion(edition, chair):
    tasks = [
        service.create_task(edition, {"title": title}, actor=as_user(chair))
        for title in ("A", "B", "C")
    ]
    # B passe en tête de « en cours », puis C devant B.
    service.update_task(tasks[1], {"status": "doing"}, actor=as_user(chair))
    service.update_task(tasks[2], {"status": "doing", "position": 0}, actor=as_user(chair))
    assert column(edition) == ["A"]
    assert column(edition, TaskStatus.DOING) == ["C", "B"]
    assert list(
        Task.objects.filter(edition=edition, status="doing")
        .order_by("position")
        .values_list("position", flat=True)
    ) == [0, 1]
    # Réordonner dans la même colonne.
    service.update_task(tasks[1], {"position": 0}, actor=as_user(chair))
    assert column(edition, TaskStatus.DOING) == ["B", "C"]
    done = service.update_task(tasks[0], {"status": "done"}, actor=as_user(chair))
    assert done.done_at is not None
    reopened = service.update_task(done, {"status": "todo"}, actor=as_user(chair))
    assert reopened.done_at is None


def test_n3_archive_and_restore_never_delete(edition, chair):
    first = service.create_task(edition, {"title": "A"}, actor=as_user(chair))
    service.create_task(edition, {"title": "B"}, actor=as_user(chair))
    archived = service.archive_task(first, actor=as_user(chair), revision=first.revision)
    assert archived.archived_at is not None and column(edition) == ["B"]
    with pytest.raises(Invalid):
        service.update_task(archived, {"title": "C"}, actor=as_user(chair))
    restored = service.restore_task(archived, actor=as_user(chair))
    assert restored.archived_at is None and column(edition) == ["B", "A"]
    assert Task.objects.filter(edition=edition).count() == 2


def test_n3_comments_and_attachments(edition, chair, settings, tmp_path):
    settings.GESTCONF_PRIVATE_FILES_DIR = str(tmp_path)
    task = service.create_task(edition, {"title": "Convention"}, actor=as_user(chair))
    with pytest.raises(Invalid):
        service.add_comment(task, "   ", actor=as_user(chair))
    comment = service.add_comment(task, " Signée. ", actor=as_user(chair))
    assert comment.body == "Signée."
    # Le journal ne garde pas le texte du commentaire.
    assert AuditLog.objects.get(action="task.commented").after in ({}, None)
    with pytest.raises(Invalid) as error:
        service.add_attachment(task, data=b"MZ\x90\x00binaire", name="x.exe", actor=as_user(chair))
    assert "file" in error.value.fields
    attachment = service.add_attachment(
        task, data=PDF, name="../convention.pdf", actor=as_user(chair)
    )
    assert attachment.kind == "pdf" and attachment.name == ".._convention.pdf"
    assert service.ATTACHMENTS.read(attachment.storage_name) == PDF
    service.remove_attachment(attachment, actor=as_user(chair))
    assert not task.attachments.exists()


def test_n3_attachment_limits(edition, chair, settings, tmp_path, monkeypatch):
    settings.GESTCONF_PRIVATE_FILES_DIR = str(tmp_path)
    task = service.create_task(edition, {"title": "Convention"}, actor=as_user(chair))
    monkeypatch.setattr(service, "ATTACHMENT_MAX_BYTES", 10)
    with pytest.raises(Invalid):
        service.add_attachment(task, data=PDF, name="gros.pdf", actor=as_user(chair))
    monkeypatch.setattr(service, "ATTACHMENT_MAX_BYTES", 10_000)
    monkeypatch.setattr(service, "ATTACHMENTS_PER_TASK", 1)
    service.add_attachment(task, data=PDF, name="a.pdf", actor=as_user(chair))
    with pytest.raises(Invalid):
        service.add_attachment(task, data=PDF, name="b.pdf", actor=as_user(chair))


def test_n3_archived_edition_is_read_only(edition, chair):
    task = service.create_task(edition, {"title": "A"}, actor=as_user(chair))
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    with pytest.raises(RuleViolation):
        service.update_task(task, {"title": "B"}, actor=as_user(chair))
    with pytest.raises(RuleViolation):
        service.create_task(edition, {"title": "C"}, actor=as_user(chair))


def test_n17_integrity_flags_missing_or_altered_attachments(edition, chair, settings, tmp_path):
    from apps.logistics import integrity

    settings.GESTCONF_PRIVATE_FILES_DIR = str(tmp_path)
    task = service.create_task(edition, {"title": "Convention"}, actor=as_user(chair))
    kept = service.add_attachment(task, data=PDF, name="a.pdf", actor=as_user(chair))
    altered = service.add_attachment(task, data=PDF, name="b.pdf", actor=as_user(chair))
    lost = service.add_attachment(task, data=PDF, name="c.pdf", actor=as_user(chair))
    service.ATTACHMENTS.path(altered.storage_name).write_bytes(PDF + b"x")
    service.ATTACHMENTS.path(lost.storage_name).unlink()
    problems = integrity.check_task_attachments()
    assert problems == [
        f"pièce jointe {altered.pk} : fichier modifié (empreinte différente)",
        f"pièce jointe {lost.pk} : fichier absent",
    ]
    assert kept.pk not in {int(item.split()[2]) for item in problems}
