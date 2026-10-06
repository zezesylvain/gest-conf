"""Sérialiseurs des soumissions, **par rôle** (règle n° 3) : vue auteur (sa propre
soumission) ; vue de gestion (``SubmissionManage*``, identité des auteurs visible des rôles
qui détiennent ``submissions.read``, F10). La vue relecteur sans identité (RG-04) est un
sérialiseur distinct, écrit en L4 avec le premier endpoint relecteur."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.services.invitations import display_name
from apps.conferences.models import SubmissionType, Track
from apps.conferences.serializers import LocalDateTimeField
from apps.submissions import services, workflow
from apps.submissions.declarations import DECLARATIONS
from apps.submissions.models import (
    StatusHistory,
    Submission,
    SubmissionAuthor,
    SubmissionExtension,
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
SUBMISSION_ACTION_CHOICES = [
    ("submit", "submit"),
    ("withdraw", "withdraw"),
    ("final_version", "final_version"),
    # Plan L5 (I5) : désigner les présentateurs et confirmer la présentation.
    ("confirm_presentation", "confirm_presentation"),
]


class AuthorReviewCommentSerializer(serializers.Serializer):
    """RG-10 : commentaire d'un relecteur, sous pseudonyme ; ni nom, ni note."""

    pseudonym_rank = serializers.IntegerField()
    comment = serializers.CharField()


class AuthorDecisionTypeSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()


class AuthorDecisionSerializer(serializers.Serializer):
    outcome = serializers.CharField(help_text="accepted, accepted_minor, waitlist, rejected.")
    assigned_type = AuthorDecisionTypeSerializer(allow_null=True)
    comment_to_authors = serializers.CharField(help_text="Message du comité.")
    published_at = serializers.DateTimeField()
    reviews = AuthorReviewCommentSerializer(many=True)


class FinalVersionSerializer(serializers.Serializer):
    submitted_at = serializers.DateTimeField()
    response_letter = serializers.CharField()
    file = SubmissionFileSerializer()


class PresentationSerializer(serializers.Serializer):
    """I5 (plan L5) : présentateurs désignés (positions des auteurs) et date de confirmation."""

    presenters = serializers.ListField(child=serializers.IntegerField(min_value=1))
    confirmed_at = serializers.DateTimeField()


class ConfirmPresentationSerializer(serializers.Serializer):
    presenters = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=50,
        help_text="Positions des auteurs qui présentent.",
    )


class FinalVersionUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    response_letter = serializers.CharField(required=False, allow_blank=True, default="")


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
    decision = serializers.SerializerMethodField(
        help_text="RG-09 : décision publiée seulement ; RG-10 : commentaires sous pseudonyme."
    )
    final_version = serializers.SerializerMethodField(help_text="Version finale déposée (H18).")
    final_deadline = serializers.SerializerMethodField(
        help_text="Date limite de la version finale (date clé camera_ready)."
    )
    presentation = serializers.SerializerMethodField(
        help_text="Confirmation de présentation (I5, plan L5)."
    )

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
            "decision",
            "final_version",
            "final_deadline",
            "presentation",
        )
        read_only_fields = fields

    @extend_schema_field(AuthorDecisionSerializer(allow_null=True))
    def get_decision(self, submission: Submission) -> dict | None:
        from apps.reviews.services.decisions import comments_for_authors, published_decision

        decision = published_decision(submission)
        if decision is None:
            return None
        return AuthorDecisionSerializer(
            {
                "outcome": decision.outcome,
                "assigned_type": decision.assigned_type,
                "comment_to_authors": decision.comment_to_authors,
                "published_at": decision.published_at,
                "reviews": comments_for_authors(submission),
            }
        ).data

    @extend_schema_field(FinalVersionSerializer(allow_null=True))
    def get_final_version(self, submission: Submission) -> dict | None:
        from apps.reviews.models import FinalVersion

        final = FinalVersion.objects.filter(submission=submission).select_related("file").first()
        return FinalVersionSerializer(final).data if final is not None else None

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_final_deadline(self, submission: Submission) -> Any:
        from apps.conferences.models import KeyDateCode

        if submission.status not in (
            SubmissionStatus.ACCEPTED,
            SubmissionStatus.ACCEPTED_MINOR,
            SubmissionStatus.CAMERA_READY_RECEIVED,
        ):
            return None
        return services.key_date(submission.edition, KeyDateCode.CAMERA_READY)

    @extend_schema_field(PresentationSerializer(allow_null=True))
    def get_presentation(self, submission: Submission) -> dict | None:
        from apps.program.models import PresentationConfirmation

        confirmation = PresentationConfirmation.objects.filter(submission=submission).first()
        return PresentationSerializer(confirmation).data if confirmation is not None else None

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
        if SubmissionStatus.CAMERA_READY_RECEIVED in targets or (
            submission.status == SubmissionStatus.CAMERA_READY_RECEIVED
        ):
            actions.append("final_version")
        if submission.status in (
            SubmissionStatus.CAMERA_READY_RECEIVED,
            SubmissionStatus.CONFIRMED,
            SubmissionStatus.SCHEDULED,
        ):
            actions.append("confirm_presentation")
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


class DuplicateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = ("id", "reference", "status", "title")
        read_only_fields = fields


class SubmissionCheckSerializer(serializers.Serializer):
    complete = serializers.BooleanField()
    missing = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))
    duplicates = DuplicateSerializer(
        many=True,
        help_text="F15 : ses autres soumissions au même titre (avertissement, non bloquant).",
    )


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


# --- Gestion (plan L3 §4, F10) -----------------------------------------------------------------


def _current_file(submission: Submission) -> SubmissionFile | None:
    """Fichier principal courant, lu dans les fichiers préchargés (pas de requête)."""
    return next(
        (f for f in submission.files.all() if f.kind == SubmissionFileKind.MAIN and f.is_current),
        None,
    )


def _active_extensions(submission: Submission, now) -> list[SubmissionExtension]:
    return [e for e in submission.extensions.all() if e.revoked_at is None and e.until > now]


class SubmissionManageSerializer(serializers.ModelSerializer):
    """Ligne de la liste de gestion : identité des auteurs (noms), sans adresse e-mail."""

    track = serializers.SlugRelatedField(slug_field="code", read_only=True, allow_null=True)
    submission_type = serializers.SlugRelatedField(
        slug_field="code", read_only=True, allow_null=True
    )
    authors_label = serializers.SerializerMethodField(
        help_text="Auteurs dans l'ordre : « Prénom Nom ; Prénom Nom »."
    )
    authors_count = serializers.SerializerMethodField()
    pages = serializers.SerializerMethodField(help_text="Pages du PDF courant (null : aucun).")
    extension_until = serializers.SerializerMethodField(
        help_text="Échéance de la dérogation en cours (RG-02), sinon null."
    )
    possible_duplicate = serializers.SerializerMethodField(
        help_text="F15 : même soumissionnaire, même titre normalisé, autre soumission active."
    )

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
            "authors_label",
            "authors_count",
            "pages",
            "extension_until",
            "possible_duplicate",
            "submitted_at",
            "updated_at",
        )
        read_only_fields = fields

    def _now(self):
        return self.context.get("now") or timezone.now()

    def _authors(self, submission: Submission) -> list[SubmissionAuthor]:
        return sorted(submission.authors.all(), key=lambda author: author.position)

    def get_authors_label(self, submission: Submission) -> str:
        return " ; ".join(
            f"{a.first_name} {a.last_name}".strip() for a in self._authors(submission)
        )

    def get_authors_count(self, submission: Submission) -> int:
        return len(submission.authors.all())

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_pages(self, submission: Submission) -> int | None:
        current = _current_file(submission)
        return current.pages if current else None

    def get_possible_duplicate(self, submission: Submission) -> bool:
        # Annotation ``has_duplicate`` de la vue (pas de requête par ligne) ; une soumission
        # retirée n'est pas signalée.
        return bool(getattr(submission, "has_duplicate", False)) and (
            submission.status != SubmissionStatus.WITHDRAWN
        )

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_extension_until(self, submission: Submission) -> Any:
        active = _active_extensions(submission, self._now())
        return max((e.until for e in active), default=None)


class ManageAuthorSerializer(SubmissionAuthorSerializer):
    """Auteur vu par la gestion : adresse comprise (contact des auteurs, F10)."""


class ExtensionSerializer(serializers.ModelSerializer):
    granted_by_name = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = SubmissionExtension
        fields = (
            "id",
            "until",
            "reason",
            "granted_by_name",
            "granted_at",
            "revoked_at",
            "is_active",
        )
        read_only_fields = fields

    def get_granted_by_name(self, extension: SubmissionExtension) -> str:
        return display_name(extension.granted_by) if extension.granted_by_id else ""

    def get_is_active(self, extension: SubmissionExtension) -> bool:
        now = self.context.get("now") or timezone.now()
        return extension.revoked_at is None and extension.until > now


class ManageHistoryEntrySerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = StatusHistory
        fields = ("from_status", "to_status", "at", "reason", "actor_name")
        read_only_fields = fields

    def get_actor_name(self, entry: StatusHistory) -> str:
        return display_name(entry.actor) if entry.actor_id else entry.actor_label


class SubmissionManageDetailSerializer(SubmissionManageSerializer):
    """Détail de gestion : métadonnées, auteurs avec adresses, fichiers, historique,
    révisions, dérogations. Réservé à ``submissions.read`` (jamais aux relecteurs, RG-04)."""

    keywords = serializers.ListField(child=serializers.CharField(), read_only=True)
    authors = ManageAuthorSerializer(many=True, read_only=True)
    submitter_name = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    declarations = serializers.SerializerMethodField()
    history = ManageHistoryEntrySerializer(source="status_history", many=True, read_only=True)
    revisions = serializers.SerializerMethodField()
    extensions = ExtensionSerializer(many=True, read_only=True)
    can_extend = serializers.SerializerMethodField(
        help_text="Une dérogation peut être accordée (brouillon ou soumise, édition non archivée)."
    )

    class Meta(SubmissionManageSerializer.Meta):
        fields = (
            *SubmissionManageSerializer.Meta.fields,
            "abstract",
            "keywords",
            "withdrawn_at",
            "withdraw_reason",
            "submitter_name",
            "authors",
            "files",
            "declarations",
            "history",
            "revisions",
            "extensions",
            "can_extend",
        )
        read_only_fields = fields

    def get_submitter_name(self, submission: Submission) -> str:
        return display_name(submission.submitter)

    @extend_schema_field(SubmissionFileSerializer(many=True))
    def get_files(self, submission: Submission) -> list[dict]:
        files = sorted(
            (f for f in submission.files.all() if f.kind == SubmissionFileKind.MAIN),
            key=lambda f: -f.version,
        )
        return SubmissionFileSerializer(files, many=True).data

    @extend_schema_field(DeclarationStateSerializer(many=True))
    def get_declarations(self, submission: Submission) -> list[dict]:
        return SubmissionSerializer().get_declarations(submission)

    @extend_schema_field(RevisionSummarySerializer(many=True))
    def get_revisions(self, submission: Submission) -> list[dict]:
        return RevisionSummarySerializer(submission.revisions.all(), many=True).data

    def get_can_extend(self, submission: Submission) -> bool:
        from apps.conferences.models import EditionStatus

        return (
            submission.status in services.EDITABLE_STATUSES
            and submission.edition.status != EditionStatus.ARCHIVED
        )


class ExtensionGrantSerializer(serializers.Serializer):
    """Dérogation (RG-02, F8) : échéance à l'heure de l'édition (D13), motif obligatoire."""

    until_local = LocalDateTimeField(
        help_text="Échéance dans le fuseau de l'édition, sans fuseau (2027-04-02T23:59)."
    )
    reason = serializers.CharField(max_length=2000)


class SubmissionStatsSerializer(serializers.Serializer):
    by_status = serializers.DictField(
        child=serializers.IntegerField(), help_text="Statut → nombre (tous les statuts)."
    )
    total = serializers.IntegerField(help_text="Soumissions hors brouillons.")
    drafts = serializers.IntegerField()
