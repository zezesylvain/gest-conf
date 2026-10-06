"""Sérialiseurs servis aux relecteurs (RG-04 ; plan L4, H9, H11). Tous dérivent des bases
relecteur de ``apps.reviews.anonymity`` : liste blanche contrôlée par le méta-test, champs
calculés justifiés. Aucun ne mène à l'identité des auteurs ; les autres relecteurs ne sont
désignés que par leur pseudonyme (« Relecteur N »)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import ClassVar

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conferences.models import SubmissionType, Track
from apps.reviews.anonymity import ReviewerModelSerializer, ReviewerSerializer
from apps.reviews.models import (
    Criterion,
    DiscussionMessage,
    EvaluationGrid,
    Recommendation,
    Review,
    ReviewAssignment,
    ReviewStatus,
)
from apps.reviews.services import reviews as review_services
from apps.submissions.models import Submission, SubmissionFileKind

SCORES_FIELD = serializers.DictField(
    child=serializers.DecimalField(max_digits=4, decimal_places=1),
    help_text="Notes par code de critère.",
)


class ReviewerTrackSerializer(ReviewerModelSerializer):
    class Meta:
        model = Track
        fields = ("code", "name_fr", "name_en")


class ReviewerTypeSerializer(ReviewerModelSerializer):
    class Meta:
        model = SubmissionType
        fields = ("code", "label_fr", "label_en")


class ReviewerCriterionSerializer(ReviewerModelSerializer):
    class Meta:
        model = Criterion
        fields = (
            "code",
            "label_fr",
            "label_en",
            "help_fr",
            "help_en",
            "weight",
            "is_required",
            "position",
        )


class ReviewerGridSerializer(ReviewerModelSerializer):
    criteria = ReviewerCriterionSerializer(many=True, read_only=True)

    class Meta:
        model = EvaluationGrid
        fields = ("id", "name", "version", "scale_min", "scale_max", "criteria")


class ReviewerSubmissionSummarySerializer(ReviewerModelSerializer):
    track = ReviewerTrackSerializer(read_only=True, allow_null=True)
    submission_type = ReviewerTypeSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Submission
        fields = ("id", "reference", "title", "language", "status", "track", "submission_type")


class ReviewerSubmissionSerializer(ReviewerSubmissionSummarySerializer):
    has_file = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        "has_file": "Présence d'un PDF courant (booléen), sans aucune métadonnée du fichier."
    }

    class Meta(ReviewerSubmissionSummarySerializer.Meta):
        fields = (
            *ReviewerSubmissionSummarySerializer.Meta.fields,
            "abstract",
            "keywords",
            "has_file",
        )

    def get_has_file(self, submission: Submission) -> bool:
        return submission.files.filter(kind=SubmissionFileKind.MAIN, is_current=True).exists()


class ReviewerReviewSerializer(ReviewerModelSerializer):
    suggested_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    scores = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        "scores": "Notes de cette évaluation par code de critère."
    }

    class Meta:
        model = Review
        fields = (
            "status",
            "recommendation",
            "confidence",
            "comment_to_authors",
            "comment_to_committee",
            "ethics_flag",
            "plagiarism_flag",
            "suggested_type",
            "weighted_score",
            "submitted_at",
            "version",
            "scores",
        )

    @extend_schema_field(SCORES_FIELD)
    def get_scores(self, review: Review) -> dict[str, Decimal]:
        return {code: str(value) for code, value in review_services.scores_of(review).items()}


class ReviewerAssignmentSerializer(ReviewerModelSerializer):
    """Ligne de « Mes évaluations »."""

    submission = ReviewerSubmissionSummarySerializer(read_only=True)
    review_status = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        "review_status": "État de sa propre évaluation (null : non commencée).",
        "can_edit": "Évaluation modifiable (affectation active, soumission en évaluation).",
    }

    class Meta:
        model = ReviewAssignment
        fields = (
            "id",
            "status",
            "assigned_at",
            "due_at",
            "pseudonym_rank",
            "submission",
            "review_status",
            "can_edit",
        )

    @extend_schema_field(serializers.ChoiceField(choices=ReviewStatus.choices, allow_null=True))
    def get_review_status(self, assignment: ReviewAssignment) -> str | None:
        review = getattr(assignment, "review", None)
        return review.status if review is not None else None

    def get_can_edit(self, assignment: ReviewAssignment) -> bool:
        return review_services.can_edit(assignment)


class ReviewerAssignmentDetailSerializer(ReviewerAssignmentSerializer):
    submission = ReviewerSubmissionSerializer(read_only=True)
    grid = serializers.SerializerMethodField()
    review = serializers.SerializerMethodField()
    discussion_open = serializers.SerializerMethodField()
    double_blind = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        **ReviewerAssignmentSerializer.reviewer_computed,
        "grid": "Grille de l'évaluation (sérialiseur relecteur ReviewerGridSerializer).",
        "review": "Sa propre évaluation (sérialiseur relecteur ReviewerReviewSerializer).",
        "discussion_open": "RG-08 : discussion ouverte et son évaluation envoyée.",
        "double_blind": "Réglage de l'édition : sans double aveugle, la route « authors » répond.",
    }

    class Meta(ReviewerAssignmentSerializer.Meta):
        fields = (
            *ReviewerAssignmentSerializer.Meta.fields,
            "grid",
            "review",
            "discussion_open",
            "double_blind",
        )

    @extend_schema_field(ReviewerGridSerializer(allow_null=True))
    def get_grid(self, assignment: ReviewAssignment):
        grid = review_services.grid_of(assignment)
        return ReviewerGridSerializer(grid).data if grid is not None else None

    @extend_schema_field(ReviewerReviewSerializer(allow_null=True))
    def get_review(self, assignment: ReviewAssignment):
        review = getattr(assignment, "review", None)
        return ReviewerReviewSerializer(review).data if review is not None else None

    def get_discussion_open(self, assignment: ReviewAssignment) -> bool:
        return review_services.can_see_discussion(assignment)

    def get_double_blind(self, assignment: ReviewAssignment) -> bool:
        return assignment.submission.edition.double_blind


class ReviewWriteSerializer(ReviewerSerializer):
    """Copie de travail envoyée par le relecteur ; la note pondérée est calculée par le
    serveur (H4), jamais lue ici."""

    reviewer_model = "reviews.Review"

    scores = serializers.DictField(
        child=serializers.DecimalField(max_digits=4, decimal_places=1, allow_null=True),
        required=False,
        default=dict,
    )
    recommendation = serializers.ChoiceField(
        choices=Recommendation.choices, required=False, allow_blank=True, default=""
    )
    confidence = serializers.IntegerField(
        min_value=1, max_value=5, required=False, allow_null=True, default=None
    )
    comment_to_authors = serializers.CharField(required=False, allow_blank=True, default="")
    comment_to_committee = serializers.CharField(required=False, allow_blank=True, default="")
    ethics_flag = serializers.BooleanField(required=False, default=False)
    plagiarism_flag = serializers.BooleanField(required=False, default=False)
    suggested_type = serializers.SlugField(required=False, allow_null=True, default=None)


class DeclineSerializer(ReviewerSerializer):
    reviewer_model = "reviews.ReviewAssignment"

    reason = serializers.CharField(max_length=2000)
    conflict = serializers.BooleanField(
        default=False, help_text="Le relecteur déclare un conflit d'intérêts (H8)."
    )


class PeerReviewSerializer(ReviewerModelSerializer):
    """Évaluation d'un autre relecteur, sous pseudonyme (RG-08, H11)."""

    pseudonym_rank = serializers.IntegerField(source="assignment.pseudonym_rank", read_only=True)
    mine = serializers.SerializerMethodField()
    suggested_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    scores = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        "mine": "Vrai pour sa propre évaluation.",
        "scores": "Notes par code de critère.",
    }

    class Meta:
        model = Review
        fields = (
            "pseudonym_rank",
            "mine",
            "recommendation",
            "confidence",
            "comment_to_authors",
            "comment_to_committee",
            "ethics_flag",
            "plagiarism_flag",
            "suggested_type",
            "weighted_score",
            "submitted_at",
            "version",
            "scores",
        )

    def get_mine(self, review: Review) -> bool:
        return review.assignment.reviewer_id == self.context.get("user_id")

    @extend_schema_field(SCORES_FIELD)
    def get_scores(self, review: Review) -> dict[str, Decimal]:
        return {code: str(value) for code, value in review_services.scores_of(review).items()}


class DiscussionMessageReviewerSerializer(ReviewerModelSerializer):
    """Message sous pseudonyme : « Relecteur N », ou le président du comité (H11)."""

    pseudonym_rank = serializers.SerializerMethodField()
    mine = serializers.SerializerMethodField()

    reviewer_computed: ClassVar[Mapping[str, str]] = {
        "pseudonym_rank": "Rang du pseudonyme de l'auteur du message (null : président).",
        "mine": "Vrai pour ses propres messages.",
    }

    class Meta:
        model = DiscussionMessage
        fields = ("id", "pseudonym_rank", "mine", "body", "at")

    def get_pseudonym_rank(self, message: DiscussionMessage) -> int | None:
        return self.context.get("ranks", {}).get(message.author_id)

    def get_mine(self, message: DiscussionMessage) -> bool:
        return message.author_id == self.context.get("user_id")


class ReviewerDiscussionSerializer(ReviewerSerializer):
    """RG-08 : évaluations envoyées (pseudonymes) et messages de la discussion."""

    reviewer_model = "reviews.Discussion"

    opened_at = serializers.DateTimeField(read_only=True)
    final_score = serializers.DecimalField(max_digits=5, decimal_places=2, allow_null=True)
    spread = serializers.DecimalField(max_digits=5, decimal_places=2)
    reviews = PeerReviewSerializer(many=True, read_only=True)
    messages = DiscussionMessageReviewerSerializer(many=True, read_only=True)


class MessageWriteSerializer(ReviewerSerializer):
    reviewer_model = "reviews.DiscussionMessage"

    body = serializers.CharField(max_length=5000)


class ExpertiseSerializer(ReviewerSerializer):
    """Expertises du relecteur (H7) et thématiques proposées."""

    reviewer_model = "reviews.ReviewerTrack"

    tracks = serializers.ListField(child=serializers.CharField(), help_text="Codes choisis.")
    available = ReviewerTrackSerializer(many=True, read_only=True)


class ExpertiseWriteSerializer(ReviewerSerializer):
    reviewer_model = "reviews.ReviewerTrack"

    tracks = serializers.ListField(child=serializers.SlugField(max_length=32), max_length=50)
