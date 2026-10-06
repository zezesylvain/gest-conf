"""Sérialiseurs de l'évaluation, par rôle (règle n° 3). Gestion ici (grilles, L4.1 ;
recevabilité et affectations, L4.2). Les sérialiseurs servis aux relecteurs dérivent de
``apps.reviews.anonymity`` (RG-04)."""

from __future__ import annotations

from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conferences.serializers import LocalDateTimeField
from apps.reviews.models import (
    ConflictKind,
    ConflictOfInterest,
    Criterion,
    EvaluationGrid,
    ReviewAssignment,
    ReviewStatus,
)
from apps.submissions.models import Submission


class CriterionSerializer(serializers.ModelSerializer):
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
        read_only_fields = ("position",)


class CriterionWriteSerializer(serializers.Serializer):
    code = serializers.SlugField(max_length=32)
    label_fr = serializers.CharField(max_length=255)
    label_en = serializers.CharField(max_length=255, required=False, allow_blank=True)
    help_fr = serializers.CharField(required=False, allow_blank=True)
    help_en = serializers.CharField(required=False, allow_blank=True)
    weight = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0.01"), max_value=Decimal("100")
    )
    is_required = serializers.BooleanField(default=True)


class GridSerializer(serializers.ModelSerializer):
    submission_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    criteria = CriterionSerializer(many=True, read_only=True)
    is_locked = serializers.SerializerMethodField(
        help_text="Utilisée par une évaluation (RG-05) : on la duplique pour la modifier."
    )

    class Meta:
        model = EvaluationGrid
        fields = (
            "id",
            "submission_type",
            "version",
            "name",
            "scale_min",
            "scale_max",
            "locked_at",
            "is_locked",
            "criteria",
        )
        read_only_fields = fields

    def get_is_locked(self, grid: EvaluationGrid) -> bool:
        return grid.locked_at is not None


class GridCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    submission_type = serializers.CharField(
        max_length=32,
        required=False,
        allow_null=True,
        help_text="Code du type ; absent ou nul : grille de tous les types.",
    )
    scale_min = serializers.IntegerField(min_value=0, max_value=99, default=0)
    scale_max = serializers.IntegerField(min_value=1, max_value=100, default=5)
    criteria = CriterionWriteSerializer(
        many=True,
        required=False,
        help_text="Liste complète ; absente : grille par défaut de l'étude (25/30/15/15/15).",
    )


class GridUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    scale_min = serializers.IntegerField(min_value=0, max_value=99, required=False)
    scale_max = serializers.IntegerField(min_value=1, max_value=100, required=False)
    criteria = CriterionWriteSerializer(
        many=True, required=False, help_text="Liste complète et ordonnée (RG-05 : somme 100)."
    )


# --- Recevabilité et affectations (président du CS, L4.2) -----------------------------------
# Servis aux détenteurs de ``reviews.manage`` seulement : noms des relecteurs (H11), jamais
# leurs adresses.


class PersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField(help_text="Nom du profil, sinon adresse masquée.")


def person(user) -> dict[str, object] | None:
    from apps.accounts.services.invitations import display_name

    return None if user is None else {"id": user.pk, "name": display_name(user)}


class AssignmentManageSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()
    assigned_by = serializers.SerializerMethodField()
    review_status = serializers.SerializerMethodField(
        help_text="Évaluation : null (non commencée), draft ou submitted."
    )

    class Meta:
        model = ReviewAssignment
        fields = (
            "id",
            "reviewer",
            "status",
            "assigned_by",
            "assigned_at",
            "due_at",
            "reason",
            "conflict_override_reason",
            "pseudonym_rank",
            "reminders",
            "review_status",
        )
        read_only_fields = fields

    @extend_schema_field(PersonSerializer)
    def get_reviewer(self, assignment: ReviewAssignment):
        return person(assignment.reviewer)

    @extend_schema_field(PersonSerializer(allow_null=True))
    def get_assigned_by(self, assignment: ReviewAssignment):
        return person(assignment.assigned_by)

    @extend_schema_field(serializers.ChoiceField(choices=ReviewStatus.choices, allow_null=True))
    def get_review_status(self, assignment: ReviewAssignment):
        review = getattr(assignment, "review", None)
        return review.status if review is not None else None


class ConflictManageSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()
    declared_by = serializers.SerializerMethodField()
    overridden_by = serializers.SerializerMethodField()

    class Meta:
        model = ConflictOfInterest
        fields = (
            "id",
            "reviewer",
            "kind",
            "source",
            "reason",
            "declared_by",
            "created_at",
            "overridden_by",
            "overridden_at",
            "overridden_reason",
        )
        read_only_fields = fields

    @extend_schema_field(PersonSerializer)
    def get_reviewer(self, conflict: ConflictOfInterest):
        return person(conflict.reviewer)

    @extend_schema_field(PersonSerializer(allow_null=True))
    def get_declared_by(self, conflict: ConflictOfInterest):
        return person(conflict.declared_by)

    @extend_schema_field(PersonSerializer(allow_null=True))
    def get_overridden_by(self, conflict: ConflictOfInterest):
        return person(conflict.overridden_by)


class ReviewSubmissionSerializer(serializers.ModelSerializer):
    """Ligne du suivi de l'évaluation : compteurs annotés par la vue."""

    track = serializers.SlugRelatedField(slug_field="code", read_only=True, allow_null=True)
    submission_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    assignment_count = serializers.IntegerField(help_text="Affectations actives.")
    review_count = serializers.IntegerField(help_text="Évaluations envoyées (actives).")
    late_count = serializers.IntegerField(help_text="Affectations actives en retard.")
    required = serializers.SerializerMethodField(help_text="Relecteurs requis (édition).")

    class Meta:
        model = Submission
        fields = (
            "id",
            "reference",
            "status",
            "title",
            "track",
            "submission_type",
            "language",
            "submitted_at",
            "assignment_count",
            "review_count",
            "late_count",
            "required",
        )
        read_only_fields = fields

    def get_required(self, submission: Submission) -> int:
        return submission.edition.reviewers_per_submission


class ReviewSubmissionDetailSerializer(ReviewSubmissionSerializer):
    assignments = AssignmentManageSerializer(many=True, read_only=True)
    conflicts = ConflictManageSerializer(many=True, read_only=True)

    class Meta(ReviewSubmissionSerializer.Meta):
        fields = (
            *ReviewSubmissionSerializer.Meta.fields,
            "abstract",
            "keywords",
            "assignments",
            "conflicts",
        )
        read_only_fields = fields


SCREENING_DECISION_CHOICES = [("admissible", "admissible"), ("reject", "reject")]


class ScreeningSerializer(serializers.Serializer):
    """H10 : recevable (ouvre l'évaluation) ou rejet motivé."""

    decision = serializers.ChoiceField(choices=SCREENING_DECISION_CHOICES)
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")


class CandidateConflictSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ConflictKind.choices)
    overridable = serializers.BooleanField()
    overridden = serializers.BooleanField()


class CandidateSerializer(serializers.Serializer):
    """Relecteur proposé pour une soumission (H6, H7, H8)."""

    id = serializers.IntegerField(source="user.pk")
    name = serializers.SerializerMethodField()
    institution = serializers.SerializerMethodField()
    load = serializers.IntegerField(help_text="Affectations actives dans l'édition.")
    tracks = serializers.ListField(child=serializers.CharField(), help_text="Expertises.")
    assignment_id = serializers.SerializerMethodField(
        help_text="Affectation active sur cette soumission, sinon null."
    )
    conflicts = CandidateConflictSerializer(many=True)

    def get_name(self, candidate) -> str:
        return person(candidate.user)["name"]

    def get_institution(self, candidate) -> str:
        profile = getattr(candidate.user, "profile", None)
        return profile.institution if profile is not None else ""

    def get_assignment_id(self, candidate) -> int | None:
        return candidate.assignment.pk if candidate.assignment is not None else None


class CandidateListSerializer(serializers.Serializer):
    max_load = serializers.IntegerField(help_text="Charge maximale par relecteur (édition).")
    track = serializers.CharField(allow_null=True, help_text="Thématique de la soumission.")
    candidates = CandidateSerializer(many=True)


class AssignmentCreateSerializer(serializers.Serializer):
    submission = serializers.IntegerField()
    reviewer = serializers.IntegerField()
    due_local = LocalDateTimeField(
        required=False,
        allow_null=True,
        help_text="Échéance dans le fuseau de l'édition, sans fuseau ; par défaut, la date "
        "clé review_deadline.",
    )
    override_reason = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default="",
        help_text="Motif de levée d'un conflit levable (réauthentification récente exigée).",
    )


class AssignmentUpdateSerializer(serializers.Serializer):
    due_local = LocalDateTimeField(help_text="Nouvelle échéance, à l'heure de l'édition.")


class AssignmentCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class ConflictCreateSerializer(serializers.Serializer):
    submission = serializers.IntegerField()
    reviewer = serializers.IntegerField()
    reason = serializers.CharField(max_length=2000)
