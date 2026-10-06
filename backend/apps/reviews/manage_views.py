"""Évaluation dans la gestion (``/v1/manage/editions/{edition_id}/…``, plan L4 §4).

``ManageViewSet`` : 401 → 404 → 403, 2FA. Grilles : lecture ``edition.read``, écriture
``grids.write`` (``ADMIN``, ``CHAIR``, ``SC_CHAIR``). Recevabilité, affectations et conflits :
``reviews.manage`` (``ADMIN``, ``CHAIR``, ``SC_CHAIR``) ; la levée d'un conflit exige une
réauthentification récente (plan L4 §6).
"""

from __future__ import annotations

import django_filters
from django.db.models import Count, F, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import (
    ManageViewSet,
    RecentAuthRequired,
    has_recent_authentication,
)
from apps.accounts.roles import Capability
from apps.conferences.models import SubmissionType
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid
from apps.reviews.models import (
    AssignmentStatus,
    ConflictOfInterest,
    EvaluationGrid,
    ReviewAssignment,
    ReviewStatus,
)
from apps.reviews.serializers import (
    AssignmentCancelSerializer,
    AssignmentCreateSerializer,
    AssignmentManageSerializer,
    AssignmentUpdateSerializer,
    CandidateListSerializer,
    ConflictCreateSerializer,
    ConflictManageSerializer,
    GridCreateSerializer,
    GridSerializer,
    GridUpdateSerializer,
    ReviewSubmissionDetailSerializer,
    ReviewSubmissionSerializer,
    ScreeningSerializer,
)
from apps.reviews.services import assignments, conflicts, grids
from apps.submissions.models import Submission, SubmissionStatus

C = Capability


class GridViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ManageViewSet):
    queryset = EvaluationGrid.objects.select_related("submission_type").prefetch_related("criteria")
    serializer_class = GridSerializer
    lookup_url_kwarg = "grid_id"
    pagination_class = None
    filter_backends = ()
    required_capabilities = {
        "list": C.EDITION_READ,
        "retrieve": C.EDITION_READ,
        "create": C.GRIDS_WRITE,
        "partial_update": C.GRIDS_WRITE,
        "destroy": C.GRIDS_WRITE,
        "duplicate": C.GRIDS_WRITE,
    }

    def get_queryset(self):
        return super().get_queryset().order_by("submission_type_id", "-version", "id")

    def _grid(self, grid_id: int) -> EvaluationGrid:
        return get_object_or_404(self.get_queryset(), pk=grid_id)

    @extend_schema(operation_id="manage_grids_list")
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(operation_id="manage_grid_retrieve")
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_grid_create",
        request=GridCreateSerializer,
        responses={201: GridSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = GridCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        submission_type = None
        if data.get("submission_type"):
            submission_type = SubmissionType.objects.filter(
                edition=self.edition, code=data["submission_type"]
            ).first()
            if submission_type is None:
                raise Invalid(fields={"submission_type": ["Code inconnu pour cette édition."]})
        grid = grids.create_grid(
            self.edition,
            name=data["name"],
            submission_type=submission_type,
            scale_min=data["scale_min"],
            scale_max=data["scale_max"],
            criteria=data.get("criteria"),
            actor=Actor.from_request(request),
        )
        return Response(GridSerializer(self._grid(grid.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_grid_update",
        request=GridUpdateSerializer,
        responses={200: GridSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, grid_id: int) -> Response:
        grid = self._grid(grid_id)
        serializer = GridUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        criteria = data.pop("criteria", None)
        grids.update_grid(grid, data, criteria=criteria, actor=Actor.from_request(request))
        return Response(GridSerializer(self._grid(grid_id)).data)

    @extend_schema(operation_id="manage_grid_delete", responses={204: None})
    def destroy(self, request: Request, edition_id: int, grid_id: int) -> Response:
        grids.delete_grid(self._grid(grid_id), actor=Actor.from_request(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_grid_duplicate", request=None, responses={201: GridSerializer}
    )
    def duplicate(self, request: Request, edition_id: int, grid_id: int) -> Response:
        """RG-05 : nouvelle version modifiable d'une grille (verrouillée ou non)."""
        grid = grids.duplicate_grid(self._grid(grid_id), actor=Actor.from_request(request))
        return Response(GridSerializer(self._grid(grid.pk)).data, status=status.HTTP_201_CREATED)


# --- Recevabilité et affectations (L4.2) ------------------------------------------------------

# Soumissions du suivi de l'évaluation : à partir de la recevabilité.
NOT_IN_REVIEW = (SubmissionStatus.DRAFT, SubmissionStatus.SUBMITTED)


def _reauthentication_required() -> exceptions.PermissionDenied:
    return exceptions.PermissionDenied(
        RecentAuthRequired.message, code=ErrorCode.REAUTHENTICATION_REQUIRED.value
    )


class ReviewSubmissionFilter(django_filters.FilterSet):
    """Statut (plusieurs), thématique et type (codes), recherche (référence, titre),
    relecteurs manquants, retards."""

    status = django_filters.MultipleChoiceFilter(
        choices=[c for c in SubmissionStatus.choices if c[0] not in NOT_IN_REVIEW]
    )
    track = django_filters.CharFilter(field_name="track__code")
    submission_type = django_filters.CharFilter(field_name="submission_type__code")
    q = django_filters.CharFilter(method="search", max_length=100)
    missing = django_filters.BooleanFilter(method="filter_missing")
    late = django_filters.BooleanFilter(method="filter_late")

    class Meta:
        model = Submission
        fields = ("status", "track", "submission_type", "q", "missing", "late")

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset
        return queryset.filter(Q(reference__icontains=value) | Q(title__icontains=value))

    def filter_missing(self, queryset, name, value):
        required = F("edition__reviewers_per_submission")
        if value:
            return queryset.filter(assignment_count__lt=required)
        return queryset.filter(assignment_count__gte=required)

    def filter_late(self, queryset, name, value):
        return queryset.filter(late_count__gt=0) if value else queryset.filter(late_count=0)


class ReviewSubmissionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ManageViewSet):
    """Suivi de l'évaluation par soumission (H6, H10)."""

    queryset = Submission.objects.select_related("edition", "track", "submission_type")
    serializer_class = ReviewSubmissionSerializer
    lookup_url_kwarg = "submission_id"
    filter_backends = (DjangoFilterBackend,)
    filterset_class = ReviewSubmissionFilter
    required_capabilities = {
        "list": C.REVIEWS_MANAGE,
        "retrieve": C.REVIEWS_MANAGE,
        "screening": C.REVIEWS_MANAGE,
        "candidates": C.REVIEWS_MANAGE,
    }

    def get_queryset(self):
        active = Q(assignments__status=AssignmentStatus.ACTIVE)
        pending = Q(assignments__review__isnull=True) | Q(
            assignments__review__status=ReviewStatus.DRAFT
        )
        return (
            super()
            .get_queryset()
            .exclude(status__in=NOT_IN_REVIEW)
            .annotate(
                assignment_count=Count("assignments", filter=active, distinct=True),
                review_count=Count(
                    "assignments",
                    filter=active & Q(assignments__review__status=ReviewStatus.SUBMITTED),
                    distinct=True,
                ),
                late_count=Count(
                    "assignments",
                    filter=active & pending & Q(assignments__due_at__lt=timezone.now()),
                    distinct=True,
                ),
            )
            .order_by(F("reference").asc(nulls_last=True), "id")
        )

    def _detail(self, submission_id: int) -> Submission:
        person = ("reviewer__profile", "declared_by__profile", "overridden_by__profile")
        queryset = self.get_queryset().prefetch_related(
            Prefetch(
                "assignments",
                queryset=ReviewAssignment.objects.select_related(
                    "reviewer__profile", "assigned_by__profile", "review"
                ).order_by("pseudonym_rank", "id"),
            ),
            Prefetch(
                "conflicts",
                queryset=ConflictOfInterest.objects.select_related(*person).order_by("id"),
            ),
        )
        return get_object_or_404(queryset, pk=submission_id)

    @extend_schema(operation_id="manage_review_submissions_list")
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_review_submission_retrieve",
        responses={200: ReviewSubmissionDetailSerializer},
    )
    def retrieve(self, request: Request, edition_id: int, submission_id: int) -> Response:
        return Response(ReviewSubmissionDetailSerializer(self._detail(submission_id)).data)

    @extend_schema(
        operation_id="manage_review_submission_screening",
        request=ScreeningSerializer,
        responses={200: ReviewSubmissionDetailSerializer},
    )
    def screening(self, request: Request, edition_id: int, submission_id: int) -> Response:
        """H10 : recevable (relecteurs requis affectés) ou rejet motivé, notifié à l'auteur."""
        submission = get_object_or_404(self.get_queryset(), pk=submission_id)
        serializer = ScreeningSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignments.screen(
            submission,
            admissible=serializer.validated_data["decision"] == "admissible",
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return Response(ReviewSubmissionDetailSerializer(self._detail(submission_id)).data)

    @extend_schema(
        operation_id="manage_review_submission_candidates",
        responses={200: CandidateListSerializer},
    )
    def candidates(self, request: Request, edition_id: int, submission_id: int) -> Response:
        """Relecteurs de l'édition : charge, expertises, affectation, conflits (H6 à H8)."""
        submission = get_object_or_404(
            Submission.objects.select_related("edition", "track")
            .prefetch_related("authors")
            .exclude(status__in=NOT_IN_REVIEW),
            edition=self.edition,
            pk=submission_id,
        )
        payload = {
            "max_load": self.edition.max_reviews_per_reviewer,
            "track": submission.track.code if submission.track else None,
            "candidates": assignments.candidates(submission),
        }
        return Response(CandidateListSerializer(payload).data)


class AssignmentViewSet(ManageViewSet):
    """Affectations (H6, H8, H15) : création, échéance, annulation motivée."""

    queryset = ReviewAssignment.objects.all()
    serializer_class = AssignmentManageSerializer
    lookup_url_kwarg = "assignment_id"
    required_capabilities = {
        "create": C.REVIEWS_MANAGE,
        "partial_update": C.REVIEWS_MANAGE,
        "cancel": C.REVIEWS_MANAGE,
    }

    def get_queryset(self):
        # Pas de champ « edition » : rattachement par la soumission.
        return ReviewAssignment.objects.filter(submission__edition=self.edition).select_related(
            "submission__edition", "reviewer__profile", "assigned_by__profile", "review"
        )

    def _assignment(self, assignment_id: int) -> ReviewAssignment:
        return get_object_or_404(self.get_queryset(), pk=assignment_id)

    def _submission(self, pk: int) -> Submission:
        submission = Submission.objects.filter(edition=self.edition, pk=pk).first()
        if submission is None:
            raise Invalid(fields={"submission": [Invalid.default_message]})
        return submission

    def _reviewer(self, pk: int) -> User:
        reviewer = User.objects.filter(pk=pk).first()
        if reviewer is None:
            raise Invalid(fields={"reviewer": [Invalid.default_message]})
        return reviewer

    @extend_schema(
        operation_id="manage_assignment_create",
        request=AssignmentCreateSerializer,
        responses={201: AssignmentManageSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        submission = self._submission(data["submission"])
        reviewer = self._reviewer(data["reviewer"])
        override_reason = data["override_reason"].strip()
        if override_reason and not has_recent_authentication(request):
            found = conflicts.blocking_conflicts(submission, reviewer)
            # Levée effective d'un conflit : réauthentification récente (plan L4 §6).
            if found and all(conflict.overridable for conflict in found):
                raise _reauthentication_required()
        assignment = assignments.assign(
            submission,
            reviewer,
            actor=Actor.from_request(request),
            due_local=data.get("due_local"),
            override_reason=override_reason,
        )
        return Response(
            AssignmentManageSerializer(self._assignment(assignment.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        operation_id="manage_assignment_update",
        request=AssignmentUpdateSerializer,
        responses={200: AssignmentManageSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        assignment = self._assignment(assignment_id)
        serializer = AssignmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignments.change_due_date(
            assignment,
            due_local=serializer.validated_data["due_local"],
            actor=Actor.from_request(request),
        )
        return Response(AssignmentManageSerializer(self._assignment(assignment_id)).data)

    @extend_schema(
        operation_id="manage_assignment_cancel",
        request=AssignmentCancelSerializer,
        responses={200: AssignmentManageSerializer},
    )
    def cancel(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        assignment = self._assignment(assignment_id)
        serializer = AssignmentCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignments.cancel_assignment(
            assignment,
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return Response(AssignmentManageSerializer(self._assignment(assignment_id)).data)


class ConflictViewSet(ManageViewSet):
    """Conflit déclaré par le président (H8) ; annule l'affectation active éventuelle."""

    queryset = ConflictOfInterest.objects.all()
    serializer_class = ConflictManageSerializer
    required_capabilities = {"create": C.REVIEWS_MANAGE}

    def get_queryset(self):
        return ConflictOfInterest.objects.filter(submission__edition=self.edition)

    @extend_schema(
        operation_id="manage_conflict_create",
        request=ConflictCreateSerializer,
        responses={201: ConflictManageSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = ConflictCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        submission = Submission.objects.filter(edition=self.edition, pk=data["submission"]).first()
        if submission is None:
            raise Invalid(fields={"submission": [Invalid.default_message]})
        reviewer = User.objects.filter(pk=data["reviewer"]).first()
        if reviewer is None:
            raise Invalid(fields={"reviewer": [Invalid.default_message]})
        conflict = conflicts.declare_conflict(
            submission, reviewer, reason=data["reason"], actor=Actor.from_request(request)
        )
        conflict = (
            self.get_queryset()
            .select_related("reviewer__profile", "declared_by__profile", "overridden_by__profile")
            .get(pk=conflict.pk)
        )
        return Response(ConflictManageSerializer(conflict).data, status=status.HTTP_201_CREATED)
