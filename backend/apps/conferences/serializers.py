"""Sérialiseurs du paramétrage (plan L1 §6, §9.3). Champs toujours explicites (§5.3)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conferences.models import Edition, EditionStatus, KeyDate, SubmissionType, Track
from apps.conferences.services import utc_to_local


class EditionSummarySerializer(serializers.ModelSerializer):
    """Sélecteur d'édition : champs non sensibles seulement (D3, §5.3)."""

    class Meta:
        model = Edition
        fields = ("id", "code", "title_fr", "title_en", "year", "status")
        read_only_fields = fields


class EditionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edition
        fields = (
            "id",
            "code",
            "slug",
            "year",
            "title_fr",
            "title_en",
            "theme_fr",
            "theme_en",
            "start_date",
            "end_date",
            "venue",
            "city",
            "country",
            "timezone",
            "status",
            "published_at",
            "archived_at",
        )
        # Statut, dates de publication : par leur service seulement (§6.3).
        read_only_fields = ("id", "status", "published_at", "archived_at")


class ConfidentialitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Edition
        fields = ("double_blind", "reviewers_per_submission")


class EditionStatusChangeSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=EditionStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class TrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = (
            "id",
            "code",
            "name_fr",
            "name_en",
            "description_fr",
            "description_en",
            "position",
            "is_active",
        )
        read_only_fields = ("id",)


class SubmissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionType
        fields = (
            "id",
            "code",
            "label_fr",
            "label_en",
            "description_fr",
            "description_en",
            "default_duration_min",
            "abstract_max_words",
            "position",
            "is_active",
        )
        read_only_fields = ("id",)


class KeyDateSerializer(serializers.ModelSerializer):
    """Lecture : ``at`` (UTC) et ``at_local`` (heure de l'édition, sans fuseau)."""

    at_local = serializers.SerializerMethodField()

    class Meta:
        model = KeyDate
        fields = ("id", "code", "at", "at_local", "label_fr", "label_en", "is_public", "position")
        read_only_fields = fields

    def get_at_local(self, instance: KeyDate) -> str:
        return utc_to_local(instance.at, instance.edition.timezone).isoformat()


class LocalDateTimeField(serializers.DateTimeField):
    """Date et heure **sans fuseau**, gardées telles quelles : le service les interprète
    dans le fuseau de l'édition (D13). Le ``DateTimeField`` de DRF leur appliquerait le
    fuseau par défaut (UTC), même avec ``default_timezone=None`` (constaté)."""

    def enforce_timezone(self, value):
        return value


class KeyDateWriteSerializer(serializers.Serializer):
    """Saisie à l'heure de l'édition (D13), convertie en UTC par le serveur."""

    code = serializers.SlugField(max_length=32)
    at_local = LocalDateTimeField(
        help_text="Date et heure dans le fuseau de l'édition, sans fuseau (2027-03-31T23:59).",
    )
    label_fr = serializers.CharField(max_length=255, required=False, allow_blank=True)
    label_en = serializers.CharField(max_length=255, required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False)
    position = serializers.IntegerField(min_value=0, max_value=32767, required=False)


class PublicTrackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Track
        fields = ("code", "name_fr", "name_en", "description_fr", "description_en")
        read_only_fields = fields


class PublicSubmissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionType
        fields = (
            "code",
            "label_fr",
            "label_en",
            "description_fr",
            "description_en",
            "default_duration_min",
            "abstract_max_words",
        )
        read_only_fields = fields


class PublicKeyDateSerializer(KeyDateSerializer):
    class Meta:
        model = KeyDate
        fields = ("code", "at", "at_local", "label_fr", "label_en")
        read_only_fields = fields


class PublicEditionSerializer(serializers.ModelSerializer):
    """Édition courante publiée (§9.3) : tracks et types actifs, dates publiques seulement."""

    tracks = serializers.SerializerMethodField()
    submission_types = serializers.SerializerMethodField()
    key_dates = serializers.SerializerMethodField()

    class Meta:
        model = Edition
        fields = (
            "code",
            "slug",
            "year",
            "title_fr",
            "title_en",
            "theme_fr",
            "theme_en",
            "start_date",
            "end_date",
            "venue",
            "city",
            "country",
            "timezone",
            "tracks",
            "submission_types",
            "key_dates",
        )
        read_only_fields = fields

    @extend_schema_field(PublicTrackSerializer(many=True))
    def get_tracks(self, edition: Edition) -> list[dict]:
        return PublicTrackSerializer(edition.tracks.filter(is_active=True), many=True).data

    @extend_schema_field(PublicSubmissionTypeSerializer(many=True))
    def get_submission_types(self, edition: Edition) -> list[dict]:
        return PublicSubmissionTypeSerializer(
            edition.submission_types.filter(is_active=True), many=True
        ).data

    @extend_schema_field(PublicKeyDateSerializer(many=True))
    def get_key_dates(self, edition: Edition) -> list[dict]:
        return PublicKeyDateSerializer(
            edition.key_dates.filter(is_public=True).select_related("edition"), many=True
        ).data
