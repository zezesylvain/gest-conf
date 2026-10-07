"""Sérialiseurs de l'organisation (plan L8 §4) : tâches (N3) et budget (N4).

Lecture seule de ``tasks.read`` ou ``budget.read`` (gestion, 2FA) : aucun champ sensible
au sens de RG-04 (aucune donnée d'auteur), noms affichés par ``display_name``.
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.services.invitations import display_name
from apps.core.money import MAX_DIGITS
from apps.logistics.models import (
    BudgetCategory,
    BudgetKind,
    BudgetSource,
    Task,
    TaskAttachment,
    TaskComment,
    TaskPriority,
    TaskStatus,
)


class TaskPersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


def task_person(user) -> dict | None:
    return None if user is None else {"id": user.pk, "name": display_name(user)}


def edition_today(edition) -> date:
    return timezone.now().astimezone(ZoneInfo(edition.timezone)).date()


class TaskSerializer(serializers.ModelSerializer):
    assignee = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()
    comment_count = serializers.IntegerField(read_only=True)
    attachment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Task
        fields = (
            "id",
            "title",
            "description",
            "status",
            "priority",
            "label",
            "assignee",
            "due_date",
            "overdue",
            "position",
            "revision",
            "created_by",
            "created_at",
            "updated_at",
            "done_at",
            "archived_at",
            "comment_count",
            "attachment_count",
        )
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(TaskPersonSerializer(allow_null=True))
    def get_assignee(task: Task) -> dict | None:
        return task_person(task.assignee)

    @staticmethod
    @extend_schema_field(TaskPersonSerializer(allow_null=True))
    def get_created_by(task: Task) -> dict | None:
        return task_person(task.created_by)

    @extend_schema_field(serializers.BooleanField())
    def get_overdue(self, task: Task) -> bool:
        if task.due_date is None or task.status == TaskStatus.DONE:
            return False
        today = self.context.get("today") or edition_today(task.edition)
        return task.due_date < today


class TaskCommentSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = TaskComment
        fields = ("id", "author", "body", "created_at")
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(TaskPersonSerializer(allow_null=True))
    def get_author(comment: TaskComment) -> dict | None:
        return task_person(comment.author)


class TaskAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.SerializerMethodField()

    class Meta:
        model = TaskAttachment
        fields = ("id", "name", "kind", "size", "uploaded_by", "created_at")
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(TaskPersonSerializer(allow_null=True))
    def get_uploaded_by(attachment: TaskAttachment) -> dict | None:
        return task_person(attachment.uploaded_by)


class TaskDetailSerializer(TaskSerializer):
    comments = TaskCommentSerializer(many=True, read_only=True)
    attachments = TaskAttachmentSerializer(many=True, read_only=True)

    class Meta(TaskSerializer.Meta):
        fields = (*TaskSerializer.Meta.fields, "comments", "attachments")
        read_only_fields = fields


class TaskWriteSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200, required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    status = serializers.ChoiceField(choices=TaskStatus.choices, required=False)
    priority = serializers.ChoiceField(choices=TaskPriority.choices, required=False)
    label = serializers.CharField(max_length=50, required=False, allow_blank=True)
    assignee = serializers.IntegerField(required=False, allow_null=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    position = serializers.IntegerField(required=False, min_value=0)


class TaskCommentWriteSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000)


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class BudgetProofSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    size = serializers.IntegerField(allow_null=True)


class BudgetLineSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=BudgetKind.choices)
    category = serializers.ChoiceField(choices=BudgetCategory.choices)
    label = serializers.CharField()
    planned = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=2)
    actual = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2, allow_null=True)
    variance = serializers.DecimalField(
        max_digits=MAX_DIGITS + 2, decimal_places=2, allow_null=True
    )
    source = serializers.ChoiceField(choices=BudgetSource.choices)
    computed = serializers.BooleanField()
    note = serializers.CharField(allow_blank=True)
    position = serializers.IntegerField()
    proof = BudgetProofSerializer(allow_null=True)


def budget_line_data(line, actual) -> dict:
    return {
        "id": line.pk,
        "kind": line.kind,
        "category": line.category,
        "label": line.label,
        "planned": line.planned,
        "actual": actual,
        "variance": None if actual is None else actual - line.planned,
        "source": line.source,
        "computed": line.source != BudgetSource.MANUAL,
        "note": line.note,
        "position": line.position,
        "proof": (
            {"name": line.proof_name, "kind": line.proof_kind, "size": line.proof_size}
            if line.proof_storage_name
            else None
        ),
    }


class BudgetTotalsSerializer(serializers.Serializer):
    planned = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)
    actual = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)


class BudgetCategoryTotalsSerializer(BudgetTotalsSerializer):
    category = serializers.ChoiceField(choices=BudgetCategory.choices)
    kind = serializers.ChoiceField(choices=BudgetKind.choices)


class BudgetSerializer(serializers.Serializer):
    currency = serializers.CharField()
    expense = BudgetTotalsSerializer()
    income = BudgetTotalsSerializer()
    balance_planned = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)
    balance_actual = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)
    by_category = BudgetCategoryTotalsSerializer(many=True)
    lines = BudgetLineSerializer(many=True)


class BudgetLineWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=BudgetKind.choices, required=False)
    category = serializers.ChoiceField(choices=BudgetCategory.choices, required=False)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)
    planned = serializers.DecimalField(
        max_digits=MAX_DIGITS, decimal_places=2, required=False, min_value=0
    )
    actual = serializers.DecimalField(
        max_digits=MAX_DIGITS, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    position = serializers.IntegerField(required=False, min_value=0)
