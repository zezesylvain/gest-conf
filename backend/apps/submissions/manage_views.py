"""Soumissions dans la gestion (``/v1/manage/editions/{edition_id}/submissions…``, plan L3 §4).

``ManageViewSet`` : 401 → 404 → 403, 2FA. Lecture ``submissions.read`` (``ADMIN``,
``CHAIR``, ``SC_CHAIR``, CO), dérogations ``submissions.extend`` et export
``submissions.export`` (``ADMIN``, ``CHAIR``, ``SC_CHAIR``). ``SC_MEMBER`` : aucun accès
avant L4. Les brouillons figurent dans la liste (titre, auteurs) : une dérogation peut
être accordée à un brouillon que la clôture a interrompu (F8).
"""

from __future__ import annotations

import django_filters
from django.db.models import F, Prefetch, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability
from apps.core.actor import Actor
from apps.submissions import services, storage
from apps.submissions.models import (
    Submission,
    SubmissionAuthor,
    SubmissionExtension,
    SubmissionFileKind,
    SubmissionRevision,
    SubmissionStatus,
)
from apps.submissions.serializers import (
    ExtensionGrantSerializer,
    SubmissionManageDetailSerializer,
    SubmissionManageSerializer,
    SubmissionStatsSerializer,
)

C = Capability
READ, EXTEND, EXPORT = C.SUBMISSIONS_READ, C.SUBMISSIONS_EXTEND, C.SUBMISSIONS_EXPORT

ORDERINGS = {
    "reference": (F("reference").asc(nulls_last=True), "id"),
    "-submitted_at": (F("submitted_at").desc(nulls_last=True), "-id"),
    "-updated_at": ("-updated_at", "-id"),
    "title": ("title", "id"),
}


class SubmissionFilter(django_filters.FilterSet):
    """Filtres de la liste et de l'export : statut (plusieurs), thématique et type (codes),
    langue, recherche (référence, titre, nom d'auteur), doublons possibles (F15), tri
    explicite et déterministe."""

    status = django_filters.MultipleChoiceFilter(choices=SubmissionStatus.choices)
    track = django_filters.CharFilter(field_name="track__code")
    submission_type = django_filters.CharFilter(field_name="submission_type__code")
    language = django_filters.CharFilter(field_name="language")
    q = django_filters.CharFilter(method="search", max_length=100)
    duplicates = django_filters.BooleanFilter(method="filter_duplicates")
    ordering = django_filters.ChoiceFilter(
        method="order", choices=[(key, key) for key in ORDERINGS], empty_label=None
    )

    class Meta:
        model = Submission
        fields = ("status", "track", "submission_type", "language", "q", "duplicates", "ordering")

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        by_author = SubmissionAuthor.objects.filter(
            Q(last_name__icontains=value) | Q(first_name__icontains=value)
        ).values("submission_id")
        return queryset.filter(
            Q(reference__icontains=value) | Q(title__icontains=value) | Q(pk__in=by_author)
        )

    def filter_duplicates(self, queryset, name, value):
        """F15 : doublons possibles (annotation ``has_duplicate``), hors soumissions retirées."""
        if value:
            return queryset.filter(has_duplicate=True).exclude(status=SubmissionStatus.WITHDRAWN)
        return queryset

    def order(self, queryset, name, value):
        return queryset.order_by(*ORDERINGS[value])


class SubmissionManageViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ManageViewSet):
    queryset = Submission.objects.select_related(
        "edition", "track", "submission_type", "submitter", "submitter__profile"
    ).prefetch_related(
        Prefetch("authors", queryset=SubmissionAuthor.objects.order_by("position")),
        "files",
        Prefetch(
            "extensions",
            queryset=SubmissionExtension.objects.select_related(
                "granted_by", "granted_by__profile"
            ),
        ),
    )
    serializer_class = SubmissionManageSerializer
    lookup_url_kwarg = "submission_id"
    filter_backends = (DjangoFilterBackend,)
    filterset_class = SubmissionFilter
    required_capabilities = {
        "list": READ,
        "retrieve": READ,
        "stats": READ,
        "file_content": READ,
        "export": EXPORT,
        "grant_extension": EXTEND,
        "revoke_extension": EXTEND,
    }

    def get_queryset(self):
        # Tri par défaut (référence, brouillons à la fin), remplacé par « ordering ».
        return (
            super()
            .get_queryset()
            .annotate(has_duplicate=services.duplicate_exists())
            .order_by(*ORDERINGS["reference"])
        )

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "now": timezone.now()}

    def _detail(self, submission_id: int) -> Submission:
        queryset = self.get_queryset().prefetch_related(
            "status_history__actor__profile",
            Prefetch("revisions", queryset=SubmissionRevision.objects.order_by("number")),
        )
        return get_object_or_404(queryset, pk=submission_id)

    @extend_schema(operation_id="manage_submissions_list")
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_submission_retrieve",
        responses={200: SubmissionManageDetailSerializer},
    )
    def retrieve(self, request: Request, edition_id: int, submission_id: int) -> Response:
        submission = self._detail(submission_id)
        return Response(
            SubmissionManageDetailSerializer(submission, context=self.get_serializer_context()).data
        )

    @extend_schema(
        operation_id="manage_submissions_stats", responses={200: SubmissionStatsSerializer}
    )
    def stats(self, request: Request, edition_id: int) -> Response:
        """Compteurs par statut (tableau de bord)."""
        counts = services.status_counts(self.edition)
        drafts = counts[SubmissionStatus.DRAFT]
        return Response(
            {"by_status": counts, "total": sum(counts.values()) - drafts, "drafts": drafts}
        )

    @extend_schema(
        operation_id="manage_submissions_export",
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """Export CSV des soumissions filtrées (mêmes filtres que la liste), journalisé."""
        queryset = self.filter_queryset(self.get_queryset())
        filters = {
            key: request.query_params.getlist(key)
            for key in SubmissionFilter.Meta.fields
            if key in request.query_params
        }
        content = services.export_csv(
            self.edition, queryset, actor=Actor.from_request(request), filters=filters
        )
        response = HttpResponse(content, content_type="text/csv; charset=utf-8")
        name = f"soumissions-{self.edition.code}-{timezone.now():%Y%m%d}.csv"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        operation_id="manage_submission_file_content",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def file_content(
        self, request: Request, edition_id: int, submission_id: int, file_id: int
    ) -> HttpResponse:
        """Une version du PDF (règle n° 8 : endpoint authentifié, jamais servi par Apache)."""
        submission = get_object_or_404(self.get_queryset(), pk=submission_id)
        stored = next(
            (
                f
                for f in submission.files.all()
                if f.pk == file_id and f.kind == SubmissionFileKind.MAIN
            ),
            None,
        )
        if stored is None:
            raise Http404
        try:
            data = storage.read(stored.storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        response = HttpResponse(data, content_type="application/pdf")
        name = submission.reference or f"brouillon-{submission.pk}"
        response["Content-Disposition"] = f'attachment; filename="{name}-v{stored.version}.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        operation_id="manage_submission_extension_grant",
        request=ExtensionGrantSerializer,
        responses={201: SubmissionManageDetailSerializer},
    )
    def grant_extension(self, request: Request, edition_id: int, submission_id: int) -> Response:
        """Dérogation RG-02 (F8), journalisée ; l'auteur en est informé par e-mail."""
        submission = get_object_or_404(self.get_queryset(), pk=submission_id)
        serializer = ExtensionGrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.grant_extension(
            submission,
            until_local=serializer.validated_data["until_local"],
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return Response(
            SubmissionManageDetailSerializer(
                self._detail(submission_id), context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        operation_id="manage_submission_extension_revoke",
        request=None,
        responses={200: SubmissionManageDetailSerializer},
    )
    def revoke_extension(
        self, request: Request, edition_id: int, submission_id: int, extension_id: int
    ) -> Response:
        submission = get_object_or_404(self.get_queryset(), pk=submission_id)
        extension = get_object_or_404(submission.extensions.all(), pk=extension_id)
        services.revoke_extension(extension, actor=Actor.from_request(request))
        return Response(
            SubmissionManageDetailSerializer(
                self._detail(submission_id), context=self.get_serializer_context()
            ).data
        )
