"""Espace relecteur (``/v1/manage/editions/{edition_id}/reviews/…``, plan L4 §4, H1).

``ManageViewSet`` : 401 → 404 → 403, 2FA (H2) ; capacité ``reviews.write``. Le relecteur ne
voit que **ses** affectations actives, sans conflit déclaré, d'une soumission en évaluation ou
décidée (RG-03) : toute autre affectation répond 404. RG-04 : réponses construites par les
sérialiseurs relecteur (liste blanche) ; routes nommées « reviewer-… », chacune couverte par
un test de fuite.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability
from apps.conferences.models import Track
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.reviews.models import DiscussionMessage, ReviewAssignment, ReviewerTrack
from apps.reviews.reviewer_serializers import (
    DeclineSerializer,
    ExpertiseSerializer,
    ExpertiseWriteSerializer,
    MessageWriteSerializer,
    ReviewerAssignmentDetailSerializer,
    ReviewerAssignmentSerializer,
    ReviewerDiscussionSerializer,
    ReviewerReviewSerializer,
    ReviewWriteSerializer,
)
from apps.reviews.services import assignments
from apps.reviews.services import reviews as services
from apps.submissions import storage
from apps.submissions.models import SubmissionAuthor, SubmissionFileKind

RW = Capability.REVIEWS_WRITE


class OpenReviewAuthorSerializer(serializers.ModelSerializer):
    """Auteurs d'une édition **sans** double aveugle (H9, Q3) : noms et affiliations, jamais
    les adresses. Volontairement hors des sérialiseurs relecteur (RG-04 ne s'applique pas) ;
    servi par la seule route « reviewer-assignments-authors », qui répond 404 en double
    aveugle."""

    class Meta:
        model = SubmissionAuthor
        fields = ("position", "first_name", "last_name", "institution", "country")
        read_only_fields = fields


class ReviewerAssignmentViewSet(ManageViewSet):
    serializer_class = ReviewerAssignmentSerializer
    lookup_url_kwarg = "assignment_id"
    pagination_class = None
    filter_backends = ()
    required_capabilities = {
        "list": RW,
        "retrieve": RW,
        "file": RW,
        "authors": RW,
        "decline": RW,
        "save_review": RW,
        "submit_review": RW,
        "discussion": RW,
        "post_message": RW,
    }

    def get_queryset(self):
        return (
            assignments.reviewer_assignments(self.request.user, self.edition, assignments.VISIBLE)
            .select_related(
                "submission__edition",
                "submission__track",
                "submission__submission_type",
                "review__grid",
                "review__suggested_type",
            )
            .prefetch_related("review__scores__criterion", "review__grid__criteria")
            .order_by("due_at", "id")
        )

    def _assignment(self, assignment_id: int) -> ReviewAssignment:
        return get_object_or_404(self.get_queryset(), pk=assignment_id)

    def _detail(self, assignment_id: int) -> Response:
        return Response(ReviewerAssignmentDetailSerializer(self._assignment(assignment_id)).data)

    @extend_schema(operation_id="reviewer_assignments_list")
    def list(self, request: Request, edition_id: int) -> Response:
        """« Mes évaluations » : affectations actives, échéances, état de l'évaluation."""
        return Response(ReviewerAssignmentSerializer(self.get_queryset(), many=True).data)

    @extend_schema(
        operation_id="reviewer_assignment_retrieve",
        responses={200: ReviewerAssignmentDetailSerializer},
    )
    def retrieve(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """Soumission anonymisée, grille, sa propre évaluation."""
        return self._detail(assignment_id)

    @extend_schema(
        operation_id="reviewer_assignment_file",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def file(self, request: Request, edition_id: int, assignment_id: int) -> HttpResponse:
        """PDF courant (règle n° 8), nettoyé de ses métadonnées en double aveugle (L3) ; nom
        de téléchargement générique : la référence (H9)."""
        submission = self._assignment(assignment_id).submission
        stored = submission.files.filter(kind=SubmissionFileKind.MAIN, is_current=True).first()
        if stored is None:
            raise Http404
        try:
            data = storage.read(stored.storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        response = HttpResponse(data, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{submission.reference}.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        operation_id="reviewer_assignment_authors",
        responses={200: OpenReviewAuthorSerializer(many=True)},
    )
    def authors(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """Auteurs, pour une édition **sans** double aveugle seulement (Q3) ; 404 sinon."""
        submission = self._assignment(assignment_id).submission
        if submission.edition.double_blind:
            raise Http404
        rows = SubmissionAuthor.objects.filter(submission=submission).order_by("position")
        return Response(OpenReviewAuthorSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="reviewer_assignment_decline",
        request=DeclineSerializer,
        responses={204: None},
    )
    def decline(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """Le relecteur décline, en déclarant au besoin un conflit d'intérêts (H8)."""
        assignment = self._assignment(assignment_id)
        serializer = DeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.decline(
            assignment,
            reason=serializer.validated_data["reason"],
            conflict=serializer.validated_data["conflict"],
            actor=Actor.from_request(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="reviewer_review_save",
        request=ReviewWriteSerializer,
        responses={200: ReviewerReviewSerializer},
    )
    def save_review(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """Brouillon (copie complète) ; note pondérée calculée par le serveur (H4)."""
        assignment = self._assignment(assignment_id)
        serializer = ReviewWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = services.save_review(
            assignment, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(ReviewerReviewSerializer(review).data)

    @extend_schema(
        operation_id="reviewer_review_submit",
        request=ReviewWriteSerializer,
        responses={200: ReviewerReviewSerializer},
    )
    def submit_review(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """Envoi (RG-06 : chaque envoi est une version) ; corps facultatif : sans corps, le
        brouillon enregistré est envoyé."""
        assignment = self._assignment(assignment_id)
        data = None
        if request.data:
            serializer = ReviewWriteSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
        review = services.submit_review(assignment, data, actor=Actor.from_request(request))
        return Response(ReviewerReviewSerializer(review).data)

    def _discussion_payload(self, assignment: ReviewAssignment) -> dict:
        if not services.can_see_discussion(assignment):
            raise RuleViolation(code=ErrorCode.DISCUSSION_CLOSED)
        submission = assignment.submission
        state = services.summary(submission)
        discussion = submission.discussion
        messages = DiscussionMessage.objects.filter(discussion=discussion).order_by("at", "id")
        return {
            "opened_at": discussion.opened_at,
            "final_score": state.final,
            "spread": state.spread,
            "reviews": state.reviews,
            "messages": list(messages),
        }

    def _discussion_context(self, assignment: ReviewAssignment) -> dict:
        return {
            "user_id": self.request.user.pk,
            "ranks": services.pseudonyms(assignment.submission),
        }

    @extend_schema(
        operation_id="reviewer_discussion_retrieve",
        responses={200: ReviewerDiscussionSerializer},
    )
    def discussion(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        """RG-08 : évaluations envoyées (pseudonymes) et messages, une fois sa propre évaluation
        envoyée et la discussion ouverte (409 ``discussion_closed`` sinon)."""
        assignment = self._assignment(assignment_id)
        payload = self._discussion_payload(assignment)
        return Response(
            ReviewerDiscussionSerializer(payload, context=self._discussion_context(assignment)).data
        )

    @extend_schema(
        operation_id="reviewer_discussion_message",
        request=MessageWriteSerializer,
        responses={201: ReviewerDiscussionSerializer},
    )
    def post_message(self, request: Request, edition_id: int, assignment_id: int) -> Response:
        assignment = self._assignment(assignment_id)
        serializer = MessageWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.post_message(
            assignment.submission,
            serializer.validated_data["body"],
            actor=Actor.from_request(request),
            assignment=assignment,
        )
        assignment = self._assignment(assignment_id)
        payload = self._discussion_payload(assignment)
        return Response(
            ReviewerDiscussionSerializer(
                payload, context=self._discussion_context(assignment)
            ).data,
            status=status.HTTP_201_CREATED,
        )


class ExpertiseViewSet(ManageViewSet):
    """Expertises du relecteur pour l'édition (H7)."""

    serializer_class = ExpertiseSerializer
    pagination_class = None
    filter_backends = ()
    required_capabilities = {"retrieve": RW, "update": RW}

    def get_queryset(self):
        return ReviewerTrack.objects.filter(user=self.request.user, edition=self.edition)

    def _payload(self) -> dict:
        chosen = list(
            self.get_queryset()
            .order_by("track__position", "track_id")
            .values_list("track__code", flat=True)
        )
        available = Track.objects.filter(edition=self.edition, is_active=True).order_by(
            "position", "id"
        )
        return {"tracks": chosen, "available": list(available)}

    @extend_schema(operation_id="reviewer_expertise_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(ExpertiseSerializer(self._payload()).data)

    @extend_schema(
        operation_id="reviewer_expertise_update",
        request=ExpertiseWriteSerializer,
        responses={200: ExpertiseSerializer},
    )
    def update(self, request: Request, edition_id: int) -> Response:
        serializer = ExpertiseWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        codes = set(serializer.validated_data["tracks"])
        tracks = list(Track.objects.filter(edition=self.edition, is_active=True, code__in=codes))
        if len(tracks) != len(codes):
            raise Invalid(fields={"tracks": [Invalid.default_message]})
        assignments.set_expertise(
            request.user, self.edition, tracks, actor=Actor.from_request(request)
        )
        return Response(ExpertiseSerializer(self._payload()).data)
