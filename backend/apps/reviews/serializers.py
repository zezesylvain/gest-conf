"""Sérialiseurs de l'évaluation, par rôle (règle n° 3). Gestion ici (grilles, L4.1). Les
sérialiseurs servis aux relecteurs dérivent de ``apps.reviews.anonymity`` (RG-04)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.reviews.models import Criterion, EvaluationGrid


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
