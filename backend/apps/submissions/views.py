"""Espace auteur de l'API (``/v1/submissions…``, plan L3 §4). Connecté (permission par
défaut) ; chaque requête ne voit que **ses** soumissions (404 sinon, règle n° 2)."""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.errors import Invalid
from apps.submissions import services, storage, workflow
from apps.submissions.models import Submission, SubmissionFileKind
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.serializers import (
    AuthorsWriteSerializer,
    SubmissionCheckSerializer,
    SubmissionCreateSerializer,
    SubmissionFileUploadSerializer,
    SubmissionSerializer,
    SubmissionWriteSerializer,
    TimelineSerializer,
    WithdrawSerializer,
)

IF_MATCH = OpenApiParameter(
    "If-Match",
    type=int,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Révision lue ; 412 « stale_revision » si la soumission a changé depuis.",
)


def _expected_revision(request: Request) -> int | None:
    value = request.headers.get("If-Match", "").strip().strip('"')
    if not value:
        return None
    if not value.isdigit():
        raise Invalid(fields={"If-Match": ["Révision entière attendue."]})
    return int(value)


class SubmissionViewSet(GenericViewSet):
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.none()
    lookup_url_kwarg = "submission_id"

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # génération du schéma
            return Submission.objects.none()
        return (
            Submission.objects.filter(submitter=self.request.user)
            .select_related("edition", "track", "submission_type")
            .prefetch_related("authors", "files")
            .order_by("-created_at", "-id")
        )

    def get_throttles(self):
        scopes = {
            "create": "submission_write",
            "partial_update": "submission_write",
            "authors": "submission_write",
            "upload": "submission_upload",
            "submit": "submission_submit",
            "withdraw": "submission_submit",
        }
        self.throttle_scope = scopes.get(self.action, "")
        return super().get_throttles() if self.throttle_scope else []

    def _submission(self, submission_id: int) -> Submission:
        return get_object_or_404(self.get_queryset(), pk=submission_id)

    def _respond(self, submission: Submission, code: int = status.HTTP_200_OK) -> Response:
        fresh = self._submission(submission.pk)
        return Response(SubmissionSerializer(fresh).data, status=code)

    @extend_schema(
        operation_id="submissions_list",
        parameters=[OpenApiParameter("edition", int, required=False)],
        responses={200: SubmissionSerializer(many=True)},
    )
    def list(self, request: Request) -> Response:
        queryset = self.get_queryset()
        edition = request.query_params.get("edition")
        if edition and edition.isdigit():
            queryset = queryset.filter(edition_id=int(edition))
        return Response(SubmissionSerializer(queryset, many=True).data)

    @extend_schema(
        operation_id="submissions_create",
        request=SubmissionCreateSerializer,
        responses={201: SubmissionSerializer},
    )
    def create(self, request: Request) -> Response:
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edition = get_object_or_404(Edition, code=serializer.validated_data["edition"])
        submission = services.create_draft(edition, actor=Actor.from_request(request))
        return self._respond(submission, status.HTTP_201_CREATED)

    @extend_schema(operation_id="submissions_retrieve", responses={200: SubmissionSerializer})
    def retrieve(self, request: Request, submission_id: int) -> Response:
        return Response(SubmissionSerializer(self._submission(submission_id)).data)

    @extend_schema(
        operation_id="submissions_update",
        parameters=[IF_MATCH],
        request=SubmissionWriteSerializer,
        responses={200: SubmissionSerializer},
    )
    def partial_update(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        serializer = SubmissionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_submission(
            submission,
            serializer.validated_data,
            actor=Actor.from_request(request),
            expected_revision=_expected_revision(request),
        )
        return self._respond(submission)

    @extend_schema(operation_id="submissions_delete", responses={204: None})
    def destroy(self, request: Request, submission_id: int) -> Response:
        services.delete_draft(self._submission(submission_id), actor=Actor.from_request(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="submissions_authors",
        parameters=[IF_MATCH],
        request=AuthorsWriteSerializer,
        responses={200: SubmissionSerializer},
    )
    def authors(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        serializer = AuthorsWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.set_authors(
            submission,
            serializer.validated_data["authors"],
            actor=Actor.from_request(request),
            expected_revision=_expected_revision(request),
        )
        return self._respond(submission)

    @extend_schema(
        operation_id="submissions_file_upload",
        parameters=[IF_MATCH],
        request={"multipart/form-data": SubmissionFileUploadSerializer},
        responses={200: SubmissionSerializer},
    )
    def upload(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        serializer = SubmissionFileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        services.upload_file(
            submission,
            data=upload.read(),
            name=upload.name,
            actor=Actor.from_request(request),
            expected_revision=_expected_revision(request),
        )
        return self._respond(submission)

    @extend_schema(
        operation_id="submissions_file_remove",
        parameters=[IF_MATCH],
        responses={200: SubmissionSerializer},
    )
    def remove_file(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        services.remove_file(
            submission,
            actor=Actor.from_request(request),
            expected_revision=_expected_revision(request),
        )
        return self._respond(submission)

    @extend_schema(
        operation_id="submissions_file_content",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def file_content(self, request: Request, submission_id: int) -> HttpResponse:
        """Fichier courant, pour son auteur (règle n° 8 : endpoint authentifié)."""
        submission = self._submission(submission_id)
        current = submission.files.filter(kind=SubmissionFileKind.MAIN, is_current=True).first()
        if current is None:
            raise Http404
        try:
            data = storage.read(current.storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        response = HttpResponse(data, content_type="application/pdf")
        name = submission.reference or f"brouillon-{submission.pk}"
        response["Content-Disposition"] = f'attachment; filename="{name}-v{current.version}.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(operation_id="submissions_check", responses={200: SubmissionCheckSerializer})
    def check(self, request: Request, submission_id: int) -> Response:
        """RG-01 : ce qui manque pour soumettre, sans rien écrire."""
        missing = services.missing_items(self._submission(submission_id))
        return Response({"complete": not missing, "missing": missing})

    @extend_schema(
        operation_id="submissions_submit", request=None, responses={200: SubmissionSerializer}
    )
    def submit(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        workflow.transition(submission, S.SUBMITTED, Actor.from_request(request))
        return self._respond(submission)

    @extend_schema(
        operation_id="submissions_withdraw",
        request=WithdrawSerializer,
        responses={200: SubmissionSerializer},
    )
    def withdraw(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        workflow.transition(
            submission,
            S.WITHDRAWN,
            Actor.from_request(request),
            reason=serializer.validated_data["reason"],
        )
        return self._respond(submission)

    @extend_schema(operation_id="submissions_timeline", responses={200: TimelineSerializer})
    def timeline(self, request: Request, submission_id: int) -> Response:
        submission = self._submission(submission_id)
        return Response(
            TimelineSerializer(
                {
                    "history": submission.status_history.all(),
                    "revisions": submission.revisions.values("number", "at"),
                }
            ).data
        )


class SubmissionFileViewSet(SubmissionViewSet):
    """Route du fichier : multipart pour le dépôt (DRF choisit les analyseurs avant de
    connaître l'action, d'où une classe dédiée)."""

    parser_classes = (MultiPartParser,)
