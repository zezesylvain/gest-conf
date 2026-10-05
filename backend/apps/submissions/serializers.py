"""Sérialiseurs des soumissions. **Vue auteur** ici (sa propre soumission) ; la vue de
gestion (L3.4) et la vue relecteur sans identité (L4, RG-04) sont des sérialiseurs
distincts (règle n° 3)."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conferences.models import SubmissionType, Track
from apps.submissions import services, workflow
from apps.submissions.declarations import DECLARATIONS
from apps.submissions.models import (
    StatusHistory,
    Submission,
    SubmissionAuthor,
    SubmissionFile,
    SubmissionFileKind,
    SubmissionStatus,
)


class SubmissionAuthorSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionAuthor
        fields = (
            "position",
            "first_name",
            "last_name",
            "email",
            "institution",
            "country",
            "is_corresponding",
            "is_presenter",
            "has_account",
        )
        read_only_fields = ("position", "has_account")

    has_account = serializers.SerializerMethodField(
        help_text="Rattaché à un compte dont l'adresse vérifiée correspond (F5)."
    )

    def get_has_account(self, author: SubmissionAuthor) -> bool:
        return author.user_id is not None


class AuthorWriteSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    institution = serializers.CharField(max_length=255, required=False, allow_blank=True)
    country = serializers.CharField(max_length=2, required=False, allow_blank=True)
    is_corresponding = serializers.BooleanField(default=False)
    is_presenter = serializers.BooleanField(default=False)


class AuthorsWriteSerializer(serializers.Serializer):
    authors = AuthorWriteSerializer(many=True)


class SubmissionFileSerializer(serializers.ModelSerializer):
    uploaded_at = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = SubmissionFile
        fields = (
            "id",
            "kind",
            "version",
            "original_name",
            "size",
            "pages",
            "metadata_removed",
            "uploaded_at",
        )
        read_only_fields = fields


class DeclarationStateSerializer(serializers.Serializer):
    code = serializers.CharField()
    accepted = serializers.BooleanField(help_text="Acceptée dans la version courante du texte.")
    text_version = serializers.CharField()


# Actions offertes à l'auteur (énumération « SubmissionAction » du schéma).
SUBMISSION_ACTION_CHOICES = [("submit", "submit"), ("withdraw", "withdraw")]


class SubmissionSerializer(serializers.ModelSerializer):
    """Vue de l'auteur sur **sa** soumission."""

    edition_code = serializers.CharField(source="edition.code", read_only=True)
    track = serializers.SlugRelatedField(slug_field="code", read_only=True, allow_null=True)
    submission_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    keywords = serializers.ListField(child=serializers.CharField(), read_only=True)
    double_blind = serializers.BooleanField(
        source="edition.double_blind",
        read_only=True,
        help_text="Double aveugle : le PDF doit être anonyme ; ses métadonnées sont retirées.",
    )
    authors = SubmissionAuthorSerializer(many=True, read_only=True)
    file = serializers.SerializerMethodField()
    declarations = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField(
        help_text="Modifiable maintenant (état, RG-02 : appel ouvert ou dérogation)."
    )
    deadline = serializers.SerializerMethodField(
        help_text="Fin de la période de modification : dérogation en cours, sinon clôture."
    )
    allowed_actions = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = (
            "id",
            "edition",
            "edition_code",
            "double_blind",
            "reference",
            "status",
            "title",
            "abstract",
            "keywords",
            "language",
            "track",
            "submission_type",
            "revision",
            "submitted_at",
            "withdrawn_at",
            "withdraw_reason",
            "created_at",
            "updated_at",
            "authors",
            "file",
            "declarations",
            "can_edit",
            "deadline",
            "allowed_actions",
        )
        read_only_fields = fields

    @extend_schema_field(SubmissionFileSerializer(allow_null=True))
    def get_file(self, submission: Submission) -> dict | None:
        current = next(
            (
                f
                for f in submission.files.all()
                if f.kind == SubmissionFileKind.MAIN and f.is_current
            ),
            None,
        )
        return SubmissionFileSerializer(current).data if current else None

    @extend_schema_field(DeclarationStateSerializer(many=True))
    def get_declarations(self, submission: Submission) -> list[dict]:
        stored = submission.declarations or {}
        return [
            {
                "code": code,
                "accepted": (stored.get(code) or {}).get("accepted") is True
                and (stored.get(code) or {}).get("text_version") == version,
                "text_version": version,
            }
            for code, version in DECLARATIONS.items()
        ]

    def _now(self):
        return self.context.get("now") or timezone.now()

    def get_can_edit(self, submission: Submission) -> bool:
        return submission.status in services.EDITABLE_STATUSES and services.can_write(
            submission, self._now()
        )

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_deadline(self, submission: Submission) -> Any:
        extension = services.active_extension(submission, self._now())
        return extension.until if extension else services.call_closed_at(submission)

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(choices=SUBMISSION_ACTION_CHOICES))
    )
    def get_allowed_actions(self, submission: Submission) -> list[str]:
        targets = workflow.allowed_targets(submission)
        actions = []
        if SubmissionStatus.SUBMITTED in targets:
            actions.append("submit")
        if SubmissionStatus.WITHDRAWN in targets:
            actions.append("withdraw")
        return actions


class SubmissionCreateSerializer(serializers.Serializer):
    edition = serializers.CharField(
        max_length=12, help_text="Code de l'édition (édition publique courante)."
    )


class SubmissionWriteSerializer(serializers.Serializer):
    """Écriture partielle (sauvegarde automatique) : valeurs incomplètes admises."""

    title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    abstract = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    keywords = serializers.ListField(
        child=serializers.CharField(max_length=200, allow_blank=True),
        required=False,
        max_length=20,
    )
    language = serializers.CharField(max_length=2, required=False, allow_blank=True)
    track = serializers.CharField(
        max_length=32,
        required=False,
        allow_null=True,
        help_text="Code de la thématique (édition de la soumission).",
    )
    submission_type = serializers.CharField(
        max_length=32,
        required=False,
        allow_null=True,
        help_text="Code du type de communication (édition de la soumission).",
    )
    declarations = serializers.DictField(
        child=serializers.BooleanField(),
        required=False,
        help_text="Code → accepté ; la version courante du texte est enregistrée.",
    )

    def _resolve(self, model, code: str | None, field: str):
        """Code → objet de l'édition de la soumission (contexte ``edition``)."""
        if code in (None, ""):
            return None
        found = model.objects.filter(edition=self.context["edition"], code=code).first()
        if found is None:
            raise serializers.ValidationError({field: ["Code inconnu pour cette édition."]})
        return found

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if "track" in attrs:
            attrs["track"] = self._resolve(Track, attrs["track"], "track")
        if "submission_type" in attrs:
            attrs["submission_type"] = self._resolve(
                SubmissionType, attrs["submission_type"], "submission_type"
            )
        return attrs


class SubmissionCheckSerializer(serializers.Serializer):
    complete = serializers.BooleanField()
    missing = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


class SubmissionFileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="PDF ; taille maximale selon le type.")


class TimelineEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = StatusHistory
        fields = ("from_status", "to_status", "at", "reason")
        read_only_fields = fields


class RevisionSummarySerializer(serializers.Serializer):
    number = serializers.IntegerField()
    at = serializers.DateTimeField()


class TimelineSerializer(serializers.Serializer):
    history = TimelineEntrySerializer(many=True)
    revisions = RevisionSummarySerializer(many=True)
