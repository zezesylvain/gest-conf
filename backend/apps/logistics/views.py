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
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text, xlsx_bytes, xlsx_response
from apps.logistics.models import (
    BudgetLine,
    Meal,
    SpeakerVisit,
    Task,
    TaskAttachment,
    TaskStatus,
    VolunteerShift,
)
from apps.logistics.serializers import (
    AssignmentWriteSerializer,
    AttachmentUploadSerializer,
    BudgetLineWriteSerializer,
    BudgetSerializer,
    DietarySummarySerializer,
    ManageVisitSerializer,
    MealSerializer,
    MealWriteSerializer,
    MyDietarySerializer,
    MyDietaryWriteSerializer,
    MyVisitSerializer,
    ShiftBoardSerializer,
    ShiftSerializer,
    ShiftWriteSerializer,
    TaskCommentWriteSerializer,
    TaskDetailSerializer,
    TaskPersonSerializer,
    TaskSerializer,
    TaskWriteSerializer,
    VisitSpeakerWriteSerializer,
    VisitStaffWriteSerializer,
    budget_line_data,
    edition_today,
    shift_data,
    task_person,
    visit_data,
)
from apps.logistics.services import budget as budget_service
from apps.logistics.services import dietary as dietary_service
from apps.logistics.services import meals as meal_service
from apps.logistics.services import shifts as shift_service
from apps.logistics.services import tasks as task_service
from apps.logistics.services import visits as visit_service
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


# --- L8.4 : logistique (venues, régimes, repas, bénévoles) -------------------------------------


class VisitViewSet(_OrganisationViewSet):
    """``…/logistics/visits`` : fiches de venue des intervenants invités (N6)."""

    serializer_class = ManageVisitSerializer
    required_capabilities = {
        "list": C.LOGISTICS_READ,
        "retrieve": C.LOGISTICS_READ,
        "partial_update": C.LOGISTICS_WRITE,
    }

    def speaker(self, user_id: int):
        user = (
            visit_service.speakers(self.edition)
            .select_related("profile")
            .filter(pk=user_id)
            .first()
        )
        if user is None:
            raise Http404
        return user

    def item(self, user, missing=None) -> dict:
        visit = visit_service.visit_of(self.edition, user)
        if missing is None:
            missing = visit_service.missing_equipment(self.edition).get(user.pk, [])
        return visit_data(self.edition, user, visit, staff=True, missing=missing)

    @extend_schema(
        operation_id="manage_visits_list", responses={200: ManageVisitSerializer(many=True)}
    )
    def list(self, request: Request, edition_id: int) -> Response:
        missing = visit_service.missing_equipment(self.edition)
        visits = {
            visit.user_id: visit for visit in SpeakerVisit.objects.filter(edition=self.edition)
        }
        people = (
            visit_service.speakers(self.edition)
            .select_related("profile")
            .order_by("profile__last_name", "profile__first_name", "pk")
        )
        data = [
            visit_data(
                self.edition,
                user,
                visits.get(user.pk),
                staff=True,
                missing=missing.get(user.pk, []),
            )
            for user in people
        ]
        return Response(ManageVisitSerializer(data, many=True).data)

    @extend_schema(operation_id="manage_visits_retrieve", responses={200: ManageVisitSerializer})
    def retrieve(self, request: Request, edition_id: int, user_id: int) -> Response:
        return Response(ManageVisitSerializer(self.item(self.speaker(user_id))).data)

    @extend_schema(
        operation_id="manage_visits_update",
        request=VisitStaffWriteSerializer,
        responses={200: ManageVisitSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, user_id: int) -> Response:
        user = self.speaker(user_id)
        serializer = VisitStaffWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        visit_service.update_by_staff(
            self.edition, user, serializer.validated_data, actor=self.actor()
        )
        return Response(ManageVisitSerializer(self.item(user)).data)


class DietaryViewSet(_OrganisationViewSet):
    """``…/logistics/dietary`` : régimes agrégés ; liste nominative en export (RG-23)."""

    serializer_class = DietarySummarySerializer
    required_capabilities = {"retrieve": C.LOGISTICS_READ, "export": C.LOGISTICS_READ}

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "export":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(operation_id="manage_dietary_summary", responses={200: DietarySummarySerializer})
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(DietarySummarySerializer(dietary_service.summary(self.edition)).data)

    @extend_schema(
        operation_id="manage_dietary_export",
        parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """RG-23 : liste nominative des régimes et allergies, journalisée, réauthentification."""
        file_format = _file_format(request)
        header, rows = dietary_service.nominative_rows(self.edition)
        record(
            "dietary.exported",
            actor=self.actor(),
            edition=self.edition,
            after={"format": file_format, "rows": len(rows)},
        )
        return _spreadsheet(file_format, header, rows, "regimes", self.edition, "Régimes")


class MealViewSet(_OrganisationViewSet):
    """``…/logistics/meals`` : repas et effectifs estimés (N8)."""

    serializer_class = MealSerializer
    required_capabilities = {
        "list": C.LOGISTICS_READ,
        "export": C.LOGISTICS_READ,
        "create": C.LOGISTICS_WRITE,
        "partial_update": C.LOGISTICS_WRITE,
        "destroy": C.LOGISTICS_WRITE,
    }

    def meal(self, meal_id: int) -> Meal:
        meal = Meal.objects.filter(pk=meal_id, edition=self.edition).select_related("edition")
        if not meal.exists():
            raise Http404
        return meal.get()

    def respond(self, code: int = status.HTTP_200_OK) -> Response:
        data = []
        for meal in Meal.objects.filter(edition=self.edition).select_related("edition"):
            item = {name: getattr(meal, name) for name in meal_service.FIELDS}
            data.append({"id": meal.pk, **item, "estimate": meal_service.estimate(meal)})
        return Response(MealSerializer(data, many=True).data, status=code)

    @extend_schema(operation_id="manage_meals_list", responses={200: MealSerializer(many=True)})
    def list(self, request: Request, edition_id: int) -> Response:
        return self.respond()

    @extend_schema(
        operation_id="manage_meals_create",
        request=MealWriteSerializer,
        responses={201: MealSerializer(many=True)},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = MealWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        meal_service.create_meal(self.edition, serializer.validated_data, actor=self.actor())
        return self.respond(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_meals_update",
        request=MealWriteSerializer,
        responses={200: MealSerializer(many=True)},
    )
    def partial_update(self, request: Request, edition_id: int, meal_id: int) -> Response:
        serializer = MealWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        meal_service.update_meal(self.meal(meal_id), serializer.validated_data, actor=self.actor())
        return self.respond()

    @extend_schema(
        operation_id="manage_meals_destroy",
        request=None,
        responses={200: MealSerializer(many=True)},
    )
    def destroy(self, request: Request, edition_id: int, meal_id: int) -> Response:
        meal_service.delete_meal(self.meal(meal_id), actor=self.actor())
        return self.respond()

    @extend_schema(
        operation_id="manage_meals_export",
        parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx", "pdf"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """Commande au traiteur : effectifs agrégés, sans nom (journalisée) ; le PDF passe par
        le générateur des rapports (L8.7)."""
        file_format = request.query_params.get("file_format", "csv")
        if file_format != "pdf":
            file_format = _file_format(request)
        header, rows = meal_service.export_rows(self.edition)
        record(
            "meal.exported",
            actor=self.actor(),
            edition=self.edition,
            after={"format": file_format, "rows": len(rows)},
        )
        if file_format == "pdf":
            from apps.reports.services import Table
            from apps.reports.views import render_tables

            now = timezone.now()
            table = Table("meals", gettext("Commande au traiteur"), header, rows)
            name = f"repas-{self.edition.code}-{now:%Y%m%d}.pdf"
            return render_tables("pdf", gettext("Repas"), self.edition, [table], name, now)
        return _spreadsheet(file_format, header, rows, "repas", self.edition, "Repas")


class ShiftViewSet(_OrganisationViewSet):
    """``…/logistics/shifts`` : postes de bénévolat et affectations (N9)."""

    serializer_class = ShiftBoardSerializer
    required_capabilities = {
        "overview": C.VOLUNTEERS_PLAN,
        "create": C.VOLUNTEERS_PLAN,
        "partial_update": C.VOLUNTEERS_PLAN,
        "destroy": C.VOLUNTEERS_PLAN,
        "assign": C.VOLUNTEERS_PLAN,
        "unassign": C.VOLUNTEERS_PLAN,
    }

    def shift(self, shift_id: int) -> VolunteerShift:
        shift = VolunteerShift.objects.filter(pk=shift_id, edition=self.edition).select_related(
            "edition"
        )
        if not shift.exists():
            raise Http404
        return shift.get()

    def board(self, code: int = status.HTTP_200_OK) -> Response:
        shifts = (
            VolunteerShift.objects.filter(edition=self.edition)
            .select_related("edition")
            .prefetch_related("assignments__volunteer__profile")
            .order_by("starts_at", "id")
        )
        people = (
            shift_service.volunteers(self.edition)
            .select_related("profile")
            .order_by("profile__last_name", "profile__first_name", "pk")
        )
        data = {
            "shifts": [shift_data(shift) for shift in shifts],
            "volunteers": [task_person(user) for user in people],
        }
        return Response(ShiftBoardSerializer(data).data, status=code)

    # Action « overview » et non « list » : la réponse est un objet (postes et bénévoles), que
    # le schéma décrirait sinon comme un tableau.
    @extend_schema(operation_id="manage_shifts_list", responses={200: ShiftBoardSerializer})
    def overview(self, request: Request, edition_id: int) -> Response:
        return self.board()

    @extend_schema(
        operation_id="manage_shifts_create",
        request=ShiftWriteSerializer,
        responses={201: ShiftBoardSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = ShiftWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift_service.create_shift(self.edition, serializer.validated_data, actor=self.actor())
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_shifts_update",
        request=ShiftWriteSerializer,
        responses={200: ShiftBoardSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, shift_id: int) -> Response:
        serializer = ShiftWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        shift_service.update_shift(
            self.shift(shift_id), serializer.validated_data, actor=self.actor()
        )
        return self.board()

    @extend_schema(
        operation_id="manage_shifts_destroy", request=None, responses={200: ShiftBoardSerializer}
    )
    def destroy(self, request: Request, edition_id: int, shift_id: int) -> Response:
        shift_service.delete_shift(self.shift(shift_id), actor=self.actor())
        return self.board()

    @extend_schema(
        operation_id="manage_shifts_assign",
        request=AssignmentWriteSerializer,
        responses={201: ShiftBoardSerializer},
    )
    def assign(self, request: Request, edition_id: int, shift_id: int) -> Response:
        serializer = AssignmentWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shift_service.assign(
            self.shift(shift_id), serializer.validated_data["volunteer"], actor=self.actor()
        )
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_shifts_unassign", request=None, responses={200: ShiftBoardSerializer}
    )
    def unassign(
        self, request: Request, edition_id: int, shift_id: int, volunteer_id: int
    ) -> Response:
        shift_service.unassign(self.shift(shift_id), volunteer_id, actor=self.actor())
        return self.board()


class MyShiftsViewSet(_OrganisationViewSet):
    """``…/me/shifts`` : « Mon planning » du bénévole (N9) et son fichier iCal."""

    serializer_class = ShiftSerializer
    required_capabilities = {"list": C.SHIFTS_OWN, "calendar": C.SHIFTS_OWN}

    @extend_schema(operation_id="manage_my_shifts", responses={200: ShiftSerializer(many=True)})
    def list(self, request: Request, edition_id: int) -> Response:
        rows = shift_service.my_shifts(self.edition, request.user)
        return Response(
            ShiftSerializer(
                [shift_data(shift, with_volunteers=False) for shift in rows], many=True
            ).data
        )

    @extend_schema(
        operation_id="manage_my_shifts_calendar",
        responses={(200, "text/calendar"): OpenApiTypes.BINARY},
    )
    def calendar(self, request: Request, edition_id: int) -> HttpResponse:
        content = shift_service.calendar(self.edition, request.user, now=timezone.now())
        response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="benevolat-{self.edition.code}.ics"'
        )
        response["Cache-Control"] = "private, no-store"
        return response


def _file_format(request: Request) -> str:
    file_format = request.query_params.get("file_format", "csv")
    if file_format not in ("csv", "xlsx"):
        raise Invalid(fields={"file_format": [_("csv ou xlsx attendu.")]})
    return file_format


def _spreadsheet(file_format, header, rows, stem, edition, title) -> HttpResponse:
    name = f"{stem}-{edition.code}-{timezone.now():%Y%m%d}.{file_format}"
    if file_format == "xlsx":
        return xlsx_response(xlsx_bytes(header, rows, title=title), name)
    return csv_response(csv_text(header, rows), name)


# --- Espace compte (portail) : « Ma venue », régime -------------------------------------------


class _MyEditionView(APIView):
    permission_classes = (IsAuthenticated,)

    def edition(self, edition_id: int) -> Edition:
        edition = Edition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise Http404
        return edition


class MyVisitView(_MyEditionView):
    """``/v1/me/editions/{id}/visit`` : « Ma venue » de l'intervenant invité (N6) ; 404 pour
    qui n'est pas intervenant invité de l'édition. Jamais la note interne du CO."""

    @extend_schema(operation_id="me_visit_retrieve", responses={200: MyVisitSerializer})
    def get(self, request: Request, edition_id: int) -> Response:
        edition = self.edition(edition_id)
        if not visit_service.is_speaker(edition, request.user):
            raise Http404
        visit = visit_service.visit_of(edition, request.user)
        return Response(
            MyVisitSerializer(visit_data(edition, request.user, visit, staff=False)).data
        )

    @extend_schema(
        operation_id="me_visit_update",
        request=VisitSpeakerWriteSerializer,
        responses={200: MyVisitSerializer},
    )
    def put(self, request: Request, edition_id: int) -> Response:
        edition = self.edition(edition_id)
        if not visit_service.is_speaker(edition, request.user):
            raise Http404
        serializer = VisitSpeakerWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        visit = visit_service.update_by_speaker(
            edition, request.user, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(
            MyVisitSerializer(visit_data(edition, request.user, visit, staff=False)).data
        )


class MyDietaryView(_MyEditionView):
    """``/v1/me/editions/{id}/dietary`` : régime alimentaire (N7, RG-23), facultatif, avec
    consentement explicite ; ``DELETE`` retire la déclaration."""

    def data(self, edition: Edition, user) -> dict:
        declaration = dietary_service.declaration_of(edition, user)
        return {
            "eligible": dietary_service.eligible(edition, user),
            "diets": declaration.diets if declaration else [],
            "allergies": declaration.allergies if declaration else "",
            "consented_at": declaration.consented_at if declaration else None,
        }

    @extend_schema(operation_id="me_dietary_retrieve", responses={200: MyDietarySerializer})
    def get(self, request: Request, edition_id: int) -> Response:
        edition = self.edition(edition_id)
        return Response(MyDietarySerializer(self.data(edition, request.user)).data)

    @extend_schema(
        operation_id="me_dietary_update",
        request=MyDietaryWriteSerializer,
        responses={200: MyDietarySerializer},
    )
    def put(self, request: Request, edition_id: int) -> Response:
        edition = self.edition(edition_id)
        serializer = MyDietaryWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dietary_service.declare(
            edition,
            request.user,
            diets=serializer.validated_data["diets"],
            allergies=serializer.validated_data.get("allergies", ""),
            consent=serializer.validated_data["consent"],
            actor=Actor.from_request(request),
        )
        return Response(MyDietarySerializer(self.data(edition, request.user)).data)

    @extend_schema(operation_id="me_dietary_withdraw", responses={200: MyDietarySerializer})
    def delete(self, request: Request, edition_id: int) -> Response:
        edition = self.edition(edition_id)
        dietary_service.withdraw(edition, request.user, actor=Actor.from_request(request))
        return Response(MyDietarySerializer(self.data(edition, request.user)).data)
