"""Routes de l'organisation (plan L8 §4), gestion ``v1/manage/editions/{id}/…`` (2FA).

- Tâches (N3) : lues et écrites par ``tasks.read`` et ``tasks.write`` (administrateur,
  Chair, tout le CO) ; ``If-Match`` porte la révision de la tâche (412 si elle a changé).
- Budget (N4) : lu par ``budget.read`` (administrateur, Chair, CO « finances »), écrit par
  ``budget.write`` (administrateur, CO « finances ») ; export CSV ou XLSX avec
  réauthentification récente, journalisé (RG-17).
"""

from __future__ import annotations

from django.db.models import Count
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text, xlsx_bytes, xlsx_response
from apps.logistics.models import BudgetLine, Task, TaskAttachment, TaskStatus
from apps.logistics.serializers import (
    AttachmentUploadSerializer,
    BudgetLineWriteSerializer,
    BudgetSerializer,
    TaskCommentWriteSerializer,
    TaskDetailSerializer,
    TaskPersonSerializer,
    TaskSerializer,
    TaskWriteSerializer,
    budget_line_data,
    edition_today,
    task_person,
)
from apps.logistics.services import budget as budget_service
from apps.logistics.services import tasks as task_service
from apps.program.views import expected_revision

IF_MATCH = OpenApiParameter(
    "If-Match",
    type=int,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Révision de la tâche lue ; 412 « stale_revision » si elle a changé (N3).",
)
FILE_KINDS = {"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png"}


def _file_response(data: bytes, kind: str, name: str) -> HttpResponse:
    response = HttpResponse(data, content_type=FILE_KINDS[kind])
    safe = "".join(c for c in name if c.isalnum() or c in "-_. ")[:120] or "fichier"
    response["Content-Disposition"] = f'attachment; filename="{safe}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _upload(request: Request) -> tuple[bytes, str]:
    serializer = AttachmentUploadSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    upload = serializer.validated_data["file"]
    if upload.size > 10 * 1024 * 1024 + 1:
        raise Invalid(fields={"file": [_("Fichier de 10 Mo au plus.")]})
    return upload.read(), upload.name or ""


class _OrganisationViewSet(ManageViewSet):
    """Base : objets de l'édition visée seulement (404 sinon). Listes courtes, lues en entier
    et ordonnées par la vue (ni pagination ni tri générique)."""

    pagination_class = None
    filter_backends = ()

    def actor(self) -> Actor:
        return Actor.from_request(self.request)


class TaskViewSet(_OrganisationViewSet):
    """``…/tasks`` : kanban des tâches du CO (N3)."""

    serializer_class = TaskSerializer
    required_capabilities = {
        "list": C.TASKS_READ,
        "retrieve": C.TASKS_READ,
        "members": C.TASKS_READ,
        "attachment": C.TASKS_READ,
        "create": C.TASKS_WRITE,
        "partial_update": C.TASKS_WRITE,
        "archive": C.TASKS_WRITE,
        "restore": C.TASKS_WRITE,
        "comment": C.TASKS_WRITE,
        "remove_attachment": C.TASKS_WRITE,
    }

    def queryset(self):
        return (
            Task.objects.filter(edition=self.edition)
            .select_related("edition", "assignee__profile", "created_by__profile")
            .annotate(
                comment_count=Count("comments", distinct=True),
                attachment_count=Count("attachments", distinct=True),
            )
        )

    def item(self, task_id: int) -> Task:
        task = self.queryset().filter(pk=task_id).first()
        if task is None:
            raise Http404
        return task

    def context(self) -> dict:
        return {"today": edition_today(self.edition)}

    def detail_response(self, task_id: int, code: int = status.HTTP_200_OK) -> Response:
        task = (
            self.queryset()
            .prefetch_related("comments__author__profile", "attachments__uploaded_by__profile")
            .get(pk=task_id)
        )
        return Response(TaskDetailSerializer(task, context=self.context()).data, status=code)

    @extend_schema(
        operation_id="manage_tasks_list",
        parameters=[
            OpenApiParameter("status", str, enum=TaskStatus.values),
            OpenApiParameter("assignee", int, description="Responsable (compte)."),
            OpenApiParameter("mine", bool, description="Mes tâches seulement."),
            OpenApiParameter("archived", bool, description="Tâches archivées (sinon actives)."),
        ],
        responses={200: TaskSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = self.queryset()
        archived = request.query_params.get("archived") in ("true", "1")
        rows = rows.filter(archived_at__isnull=not archived)
        if request.query_params.get("status") in TaskStatus.values:
            rows = rows.filter(status=request.query_params["status"])
        assignee = request.query_params.get("assignee", "")
        if assignee.isdigit():
            rows = rows.filter(assignee_id=int(assignee))
        if request.query_params.get("mine") in ("true", "1"):
            rows = rows.filter(assignee=request.user)
        rows = rows.order_by("status", "position", "id")
        return Response(TaskSerializer(rows, many=True, context=self.context()).data)

    @extend_schema(
        operation_id="manage_tasks_members", responses={200: TaskPersonSerializer(many=True)}
    )
    def members(self, request: Request, edition_id: int) -> Response:
        people = (
            task_service.task_members(self.edition)
            .select_related("profile")
            .order_by("profile__last_name", "profile__first_name", "pk")
        )
        return Response([task_person(user) for user in people])

    @extend_schema(
        operation_id="manage_tasks_create",
        request=TaskWriteSerializer,
        responses={201: TaskDetailSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = TaskWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = task_service.create_task(self.edition, serializer.validated_data, actor=self.actor())
        return self.detail_response(task.pk, status.HTTP_201_CREATED)

    @extend_schema(operation_id="manage_tasks_retrieve", responses={200: TaskDetailSerializer})
    def retrieve(self, request: Request, edition_id: int, task_id: int) -> Response:
        self.item(task_id)
        return self.detail_response(task_id)

    @extend_schema(
        operation_id="manage_tasks_update",
        parameters=[IF_MATCH],
        request=TaskWriteSerializer,
        responses={200: TaskDetailSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, task_id: int) -> Response:
        task = self.item(task_id)
        serializer = TaskWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        task_service.update_task(
            task,
            serializer.validated_data,
            actor=self.actor(),
            revision=expected_revision(request),
        )
        return self.detail_response(task_id)

    @extend_schema(
        operation_id="manage_tasks_archive",
        parameters=[IF_MATCH],
        request=None,
        responses={200: TaskDetailSerializer},
    )
    def archive(self, request: Request, edition_id: int, task_id: int) -> Response:
        task_service.archive_task(
            self.item(task_id), actor=self.actor(), revision=expected_revision(request)
        )
        return self.detail_response(task_id)

    @extend_schema(
        operation_id="manage_tasks_restore",
        parameters=[IF_MATCH],
        request=None,
        responses={200: TaskDetailSerializer},
    )
    def restore(self, request: Request, edition_id: int, task_id: int) -> Response:
        task_service.restore_task(
            self.item(task_id), actor=self.actor(), revision=expected_revision(request)
        )
        return self.detail_response(task_id)

    @extend_schema(
        operation_id="manage_tasks_comment",
        request=TaskCommentWriteSerializer,
        responses={201: TaskDetailSerializer},
    )
    def comment(self, request: Request, edition_id: int, task_id: int) -> Response:
        serializer = TaskCommentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task_service.add_comment(
            self.item(task_id), serializer.validated_data["body"], actor=self.actor()
        )
        return self.detail_response(task_id, status.HTTP_201_CREATED)

    def _attachment(self, task_id: int, attachment_id: int) -> TaskAttachment:
        attachment = (
            TaskAttachment.objects.filter(
                pk=attachment_id, task_id=task_id, task__edition=self.edition
            )
            .select_related("task__edition")
            .first()
        )
        if attachment is None:
            raise Http404
        return attachment

    @extend_schema(
        operation_id="manage_tasks_attachments_download",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def attachment(
        self, request: Request, edition_id: int, task_id: int, attachment_id: int
    ) -> HttpResponse:
        """Pièce jointe (règle n° 8 : endpoint authentifié, type vérifié au dépôt)."""
        attachment = self._attachment(task_id, attachment_id)
        try:
            data = task_service.ATTACHMENTS.read(attachment.storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        return _file_response(data, attachment.kind, attachment.name)

    @extend_schema(
        operation_id="manage_tasks_attachments_remove",
        request=None,
        responses={200: TaskDetailSerializer},
    )
    def remove_attachment(
        self, request: Request, edition_id: int, task_id: int, attachment_id: int
    ) -> Response:
        task_service.remove_attachment(self._attachment(task_id, attachment_id), actor=self.actor())
        return self.detail_response(task_id)


class TaskAttachmentUploadViewSet(TaskViewSet):
    """``…/tasks/{id}/attachments`` (POST) : dépôt d'une pièce jointe (multipart)."""

    parser_classes = (MultiPartParser,)
    required_capabilities = {"upload": C.TASKS_WRITE}

    @extend_schema(
        operation_id="manage_tasks_attachments_upload",
        request={"multipart/form-data": AttachmentUploadSerializer},
        responses={201: TaskDetailSerializer},
    )
    def upload(self, request: Request, edition_id: int, task_id: int) -> Response:
        data, name = _upload(request)
        task_service.add_attachment(self.item(task_id), data=data, name=name, actor=self.actor())
        return self.detail_response(task_id, status.HTTP_201_CREATED)


class BudgetViewSet(_OrganisationViewSet):
    """``…/budget`` : budget prévisionnel et réalisé (N4)."""

    serializer_class = BudgetSerializer
    required_capabilities = {
        "retrieve": C.BUDGET_READ,
        "export": C.BUDGET_READ,
        "create": C.BUDGET_WRITE,
        "partial_update": C.BUDGET_WRITE,
        "destroy": C.BUDGET_WRITE,
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "export":
            permissions.append(RecentAuthRequired())
        return permissions

    def line(self, line_id: int) -> BudgetLine:
        line = (
            BudgetLine.objects.filter(pk=line_id, edition=self.edition)
            .select_related("edition")
            .first()
        )
        if line is None:
            raise Http404
        return line

    def budget(self, code: int = status.HTTP_200_OK) -> Response:
        data = budget_service.summary(self.edition)
        data["lines"] = [
            budget_line_data(line, actual) for line, actual in budget_service.lines(self.edition)
        ]
        return Response(BudgetSerializer(data).data, status=code)

    @extend_schema(operation_id="manage_budget_retrieve", responses={200: BudgetSerializer})
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return self.budget()

    @extend_schema(
        operation_id="manage_budget_lines_create",
        request=BudgetLineWriteSerializer,
        responses={201: BudgetSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = BudgetLineWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        budget_service.create_line(self.edition, serializer.validated_data, actor=self.actor())
        return self.budget(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_budget_lines_update",
        request=BudgetLineWriteSerializer,
        responses={200: BudgetSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, line_id: int) -> Response:
        serializer = BudgetLineWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        budget_service.update_line(
            self.line(line_id), serializer.validated_data, actor=self.actor()
        )
        return self.budget()

    @extend_schema(
        operation_id="manage_budget_lines_destroy", request=None, responses={200: BudgetSerializer}
    )
    def destroy(self, request: Request, edition_id: int, line_id: int) -> Response:
        budget_service.delete_line(self.line(line_id), actor=self.actor())
        return self.budget()

    @extend_schema(
        operation_id="manage_budget_export",
        parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """Export du budget (RG-17 : journalisé, réauthentification récente)."""
        file_format = request.query_params.get("file_format", "csv")
        if file_format not in ("csv", "xlsx"):
            raise Invalid(fields={"file_format": [_("csv ou xlsx attendu.")]})
        header, rows = budget_service.export_rows(self.edition)
        budget_service.record_export(
            self.edition, actor=self.actor(), file_format=file_format, count=len(rows)
        )
        stamp = timezone.now().strftime("%Y%m%d")
        name = f"budget-{self.edition.code}-{stamp}.{file_format}"
        if file_format == "xlsx":
            return xlsx_response(xlsx_bytes(header, rows, title="Budget"), name)
        return csv_response(csv_text(header, rows), name)


class BudgetProofViewSet(BudgetViewSet):
    """``…/budget/lines/{id}/proof`` : justificatif d'une ligne (lecture, dépôt multipart,
    retrait)."""

    parser_classes = (MultiPartParser,)
    required_capabilities = {
        "proof": C.BUDGET_READ,
        "upload_proof": C.BUDGET_WRITE,
        "remove_proof": C.BUDGET_WRITE,
    }

    @extend_schema(
        operation_id="manage_budget_lines_proof_upload",
        request={"multipart/form-data": AttachmentUploadSerializer},
        responses={200: BudgetSerializer},
    )
    def upload_proof(self, request: Request, edition_id: int, line_id: int) -> Response:
        data, name = _upload(request)
        budget_service.upload_proof(self.line(line_id), data=data, name=name, actor=self.actor())
        return self.budget()

    @extend_schema(
        operation_id="manage_budget_lines_proof_remove",
        request=None,
        responses={200: BudgetSerializer},
    )
    def remove_proof(self, request: Request, edition_id: int, line_id: int) -> Response:
        budget_service.remove_proof(self.line(line_id), actor=self.actor())
        return self.budget()

    @extend_schema(
        operation_id="manage_budget_lines_proof_download",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def proof(self, request: Request, edition_id: int, line_id: int) -> HttpResponse:
        line = self.line(line_id)
        if not line.proof_storage_name:
            raise Http404
        try:
            data = budget_service.PROOFS.read(line.proof_storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        return _file_response(data, line.proof_kind, line.proof_name)
