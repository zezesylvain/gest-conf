"""Sérialiseurs du jour J et des attestations (plan L7 §4)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.services.invitations import display_name
from apps.events.models import (
    Checkin,
    CheckinMethod,
    DocumentNature,
    Signature,
    SignatureLayout,
    SigningMode,
)
from apps.events.services import checkin as checkin_services
from apps.events.services.checkin import OUTCOME_CHOICES
from apps.registrations.models import Registration, RegistrationStatus, RetiredTokenReason
from apps.submissions.models import SubmissionStatus


class SignatureSerializer(serializers.Serializer):
    """Signature du signataire connecté (K18) : jamais le nom de stockage de l'image."""

    display_name = serializers.CharField(max_length=150, allow_blank=True)
    title_fr = serializers.CharField(max_length=200, allow_blank=True)
    title_en = serializers.CharField(max_length=200, allow_blank=True)
    has_image = serializers.BooleanField(read_only=True)
    image_width = serializers.IntegerField(read_only=True, allow_null=True)
    image_height = serializers.IntegerField(read_only=True, allow_null=True)
    image_uploaded_at = serializers.DateTimeField(read_only=True, allow_null=True)
    complete = serializers.BooleanField(
        read_only=True, help_text="Nom, fonction en français et image : désignable."
    )
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)


def signature_data(signature: Signature | None) -> dict:
    if signature is None:
        return {
            "display_name": "",
            "title_fr": "",
            "title_en": "",
            "has_image": False,
            "image_width": None,
            "image_height": None,
            "image_uploaded_at": None,
            "complete": False,
            "updated_at": None,
        }
    return {
        "display_name": signature.display_name,
        "title_fr": signature.title_fr,
        "title_en": signature.title_en,
        "has_image": bool(signature.image_storage_name),
        "image_width": signature.image_width,
        "image_height": signature.image_height,
        "image_uploaded_at": signature.image_uploaded_at,
        "complete": signature.is_complete,
        "updated_at": signature.updated_at,
    }


class SignatureImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


# --- Pointage (plan L7, K4, K5) -----------------------------------------------------------------


class CheckinPersonSerializer(serializers.Serializer):
    """Personne pointée : référence, nom, catégorie, statut ; ni adresse ni institution."""

    id = serializers.IntegerField()
    reference = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    category_label_fr = serializers.CharField()
    category_label_en = serializers.CharField()
    status = serializers.ChoiceField(choices=RegistrationStatus.choices)


class CheckinSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    scanned_at = serializers.DateTimeField()
    received_at = serializers.DateTimeField()
    method = serializers.ChoiceField(choices=CheckinMethod.choices)
    recorded_by = serializers.CharField()
    device = serializers.CharField()
    cancelled_at = serializers.DateTimeField(allow_null=True)
    cancelled_by = serializers.CharField()
    cancel_reason = serializers.CharField()


class CheckinResultSerializer(serializers.Serializer):
    outcome = serializers.ChoiceField(choices=OUTCOME_CHOICES)
    idempotency_key = serializers.CharField()
    registration = CheckinPersonSerializer(allow_null=True)
    checkin = CheckinSerializer(allow_null=True)


class CheckinListItemSerializer(CheckinSerializer):
    registration = CheckinPersonSerializer()


def person_data(registration: Registration | None) -> dict | None:
    if registration is None:
        return None
    return {
        "id": registration.pk,
        "reference": registration.reference,
        "name": checkin_services.person_name(registration),
        "category": registration.category.code,
        "category_label_fr": registration.category.label_fr,
        "category_label_en": registration.category.label_en or registration.category.label_fr,
        "status": registration.status,
    }


def checkin_data(checkin: Checkin | None) -> dict | None:
    if checkin is None:
        return None
    return {
        "id": checkin.pk,
        "scanned_at": checkin.scanned_at,
        "received_at": checkin.received_at,
        "method": checkin.method,
        "recorded_by": display_name(checkin.recorded_by),
        "device": checkin.device,
        "cancelled_at": checkin.cancelled_at,
        "cancelled_by": display_name(checkin.cancelled_by),
        "cancel_reason": checkin.cancel_reason,
    }


def result_data(result: checkin_services.CheckinResult) -> dict:
    return {
        "outcome": result.outcome,
        "idempotency_key": result.idempotency_key,
        "registration": person_data(result.registration),
        "checkin": checkin_data(result.checkin),
    }


IDEMPOTENCY_HELP = "Clé de l'appareil (8 à 64 caractères [A-Za-z0-9_-]) ; rejouable."


class ScanRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, help_text="Texte lu dans le QR du badge.")
    device = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default="", help_text=IDEMPOTENCY_HELP
    )


class ManualRequestSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=32, help_text="Référence « GC27-I00042 ».")
    device = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default="", help_text=IDEMPOTENCY_HELP
    )


class SyncItemSerializer(serializers.Serializer):
    idempotency_key = serializers.RegexField(
        checkin_services.IDEMPOTENCY_KEY, help_text=IDEMPOTENCY_HELP
    )
    method = serializers.ChoiceField(choices=CheckinMethod.choices, default=CheckinMethod.SCAN)
    token = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")
    reference = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    scanned_at = serializers.DateTimeField(help_text="Heure de l'appareil au pointage.")
    session = serializers.IntegerField(
        required=False, allow_null=True, default=None, help_text="Session ; vide : accueil."
    )

    def validate(self, attrs):
        field = "token" if attrs["method"] == CheckinMethod.SCAN else "reference"
        if not attrs[field]:
            raise serializers.ValidationError({field: _("Champ obligatoire.")})
        return attrs


class SyncRequestSerializer(serializers.Serializer):
    device = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    items = SyncItemSerializer(many=True, max_length=checkin_services.SYNC_MAX_ITEMS)


class SyncResponseSerializer(serializers.Serializer):
    results = CheckinResultSerializer(many=True)


class BundleCategorySerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()


class BundleEntrySerializer(serializers.Serializer):
    token_hash = serializers.CharField(help_text="SHA-256 (hexadécimal) du texte du QR.")
    reference = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    checked_in = serializers.BooleanField()


class BundleRetiredSerializer(serializers.Serializer):
    token_hash = serializers.CharField()
    reference = serializers.CharField()
    reason = serializers.ChoiceField(choices=RetiredTokenReason.choices)


class BundleSerializer(serializers.Serializer):
    """Liste de pointage hors ligne (K5) : minimale, sans jeton, à effacer après 48 h."""

    edition_id = serializers.IntegerField()
    generated_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    categories = BundleCategorySerializer(many=True)
    entries = BundleEntrySerializer(many=True)
    retired = BundleRetiredSerializer(many=True)


class CheckinSummarySerializer(serializers.Serializer):
    confirmed = serializers.IntegerField()
    checked_in = serializers.IntegerField()
    pending = serializers.IntegerField()


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500)


class BadgeBatchesSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    batch_size = serializers.IntegerField()
    batches = serializers.IntegerField()


# --- Émargement des sessions et communications présentées (K7, K8) ---------------------------


class DaySlotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    title = serializers.CharField()
    reference = serializers.CharField()
    submission_id = serializers.IntegerField(allow_null=True)
    presenters = serializers.ListField(child=serializers.CharField())
    status = serializers.ChoiceField(
        choices=SubmissionStatus.choices,
        allow_blank=True,
        help_text="Statut courant de la communication (vide : élément libre).",
    )


class DaySessionSerializer(serializers.Serializer):
    """Session du programme publié, pour l'émargement (K7) et « présentée » (K8)."""

    id = serializers.IntegerField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    room = serializers.CharField()
    chairs = serializers.ListField(child=serializers.CharField())
    chaired = serializers.BooleanField(help_text="Le compte connecté préside la session.")
    attendance = serializers.IntegerField(help_text="Présents pointés à l'entrée.")
    slots = DaySlotSerializer(many=True)


class SessionScanRequestSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128, help_text="Texte lu dans le QR du badge.")
    device = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default="", help_text=IDEMPOTENCY_HELP
    )


# --- Attestations (K9 à K11, K18, K19) -----------------------------------------------------


class SigningKeySerializer(serializers.Serializer):
    subject = serializers.CharField()
    not_after = serializers.DateTimeField(allow_null=True)
    uploaded_at = serializers.DateTimeField(allow_null=True)


class CertificateSettingsSerializer(serializers.Serializer):
    """Paramètres des pièces : jamais le certificat ni l'image eux-mêmes."""

    signing_mode = serializers.ChoiceField(choices=SigningMode.choices)
    review_enabled = serializers.BooleanField()
    layout = serializers.ChoiceField(choices=SignatureLayout.choices)
    has_header = serializers.BooleanField(read_only=True)
    header_width = serializers.IntegerField(read_only=True, allow_null=True)
    header_height = serializers.IntegerField(read_only=True, allow_null=True)
    signing_key = SigningKeySerializer(read_only=True, allow_null=True)
    signing_available = serializers.BooleanField(
        read_only=True, help_text="Clés de chiffrement du certificat configurées (serveur)."
    )


def certificate_settings_data(current) -> dict:
    from apps.events.services.certificates import signing_available

    return {
        "signing_mode": current.signing_mode,
        "review_enabled": current.review_enabled,
        "layout": current.layout,
        "has_header": bool(current.header_storage_name),
        "header_width": current.header_width,
        "header_height": current.header_height,
        "signing_key": {
            "subject": current.key_subject,
            "not_after": current.key_not_after,
            "uploaded_at": current.key_uploaded_at,
        }
        if current.key_storage_name
        else None,
        "signing_available": signing_available(),
    }


class ImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class SigningKeyUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Certificat de l'institution (PKCS#12, .p12 ou .pfx).")
    password = serializers.CharField(
        max_length=256, allow_blank=True, trim_whitespace=False, write_only=True
    )


class SignatorySerializer(serializers.Serializer):
    """Signature désignable (K18) : jamais l'image ni son empreinte."""

    id = serializers.IntegerField()
    display_name = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()


def signatory_data(signature) -> dict | None:
    if signature is None:
        return None
    return {
        "id": signature.pk,
        "display_name": signature.display_name,
        "title_fr": signature.title_fr,
        "title_en": signature.title_en,
    }


class TemplateCustomizedSerializer(serializers.Serializer):
    title_fr = serializers.BooleanField()
    title_en = serializers.BooleanField()
    body_fr = serializers.BooleanField()
    body_en = serializers.BooleanField()
    footer_fr = serializers.BooleanField()
    footer_en = serializers.BooleanField()


class DocumentTemplateSerializer(serializers.Serializer):
    """Gabarit effectif d'une nature (textes par défaut là où rien n'est saisi)."""

    nature = serializers.ChoiceField(choices=DocumentNature.choices)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    body_fr = serializers.CharField()
    body_en = serializers.CharField()
    footer_fr = serializers.CharField(allow_blank=True)
    footer_en = serializers.CharField(allow_blank=True)
    customized = TemplateCustomizedSerializer()
    placeholders = serializers.ListField(child=serializers.CharField())
    signatory = SignatorySerializer(allow_null=True)


def template_data(view) -> dict:
    from apps.events.texts import PLACEHOLDERS

    return {
        "nature": view.nature,
        **view.texts,
        "customized": view.customized,
        "placeholders": sorted(PLACEHOLDERS[view.nature]),
        "signatory": signatory_data(view.signatory),
    }


class DocumentTemplateUpdateSerializer(serializers.Serializer):
    title_fr = serializers.CharField(max_length=200, allow_blank=True, required=False)
    title_en = serializers.CharField(max_length=200, allow_blank=True, required=False)
    body_fr = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    body_en = serializers.CharField(max_length=2000, allow_blank=True, required=False)
    footer_fr = serializers.CharField(max_length=500, allow_blank=True, required=False)
    footer_en = serializers.CharField(max_length=500, allow_blank=True, required=False)
    signatory = serializers.IntegerField(
        required=False, allow_null=True, help_text="Signature désignée (null : aucune)."
    )


class CertificateOverviewSerializer(serializers.Serializer):
    nature = serializers.ChoiceField(choices=DocumentNature.choices)
    enabled = serializers.BooleanField()
    ready = serializers.BooleanField(help_text="Conditions de l'émission réunies.")
    problem = serializers.CharField(allow_blank=True, help_text="Code d'erreur sinon.")
    eligible = serializers.IntegerField(help_text="Personnes remplissant RG-16.")
    issued = serializers.IntegerField()
    revoked = serializers.IntegerField()
    unreachable = serializers.IntegerField(help_text="Présentateurs sans compte.")
    pending = serializers.BooleanField(help_text="Émission en cours dans la file.")


# Natures d'attestation (sans la lettre d'invitation) ; statut et type de la vérification.
CERTIFICATE_NATURE_CHOICES = [
    (value, label) for value, label in DocumentNature.choices if value != DocumentNature.LETTER
]
VERIFICATION_KIND_CHOICES = [("certificate", "certificate"), ("letter", "letter")]
VERIFICATION_STATUS_CHOICES = [("valid", "valid"), ("revoked", "revoked")]


class IssueRequestSerializer(serializers.Serializer):
    nature = serializers.ChoiceField(choices=CERTIFICATE_NATURE_CHOICES)


class IssueResponseSerializer(serializers.Serializer):
    job_id = serializers.IntegerField()


class CertificateSerializer(serializers.Serializer):
    """Attestation (gestion) : sans nom de stockage ni empreinte."""

    id = serializers.IntegerField()
    nature = serializers.ChoiceField(choices=DocumentNature.choices)
    user_id = serializers.IntegerField()
    name = serializers.CharField()
    institution = serializers.CharField()
    reference = serializers.CharField(allow_blank=True)
    signing_mode = serializers.ChoiceField(choices=SigningMode.choices)
    signatory_name = serializers.CharField()
    issued_at = serializers.DateTimeField()
    revoked_at = serializers.DateTimeField(allow_null=True)
    revoke_reason = serializers.CharField()


def certificate_data(row) -> dict:
    return {
        "id": row.pk,
        "nature": row.nature,
        "user_id": row.user_id,
        "name": row.name,
        "institution": row.institution,
        "reference": row.details.get("reference", ""),
        "signing_mode": row.signing_mode,
        "signatory_name": row.signatory_name,
        "issued_at": row.issued_at,
        "revoked_at": row.revoked_at,
        "revoke_reason": row.revoke_reason,
    }


class MyCertificateSerializer(serializers.Serializer):
    """Attestation de la personne connectée (« Mes documents »)."""

    id = serializers.IntegerField()
    nature = serializers.ChoiceField(choices=DocumentNature.choices)
    edition_code = serializers.CharField()
    edition_title_fr = serializers.CharField()
    edition_title_en = serializers.CharField()
    title = serializers.CharField(
        allow_blank=True, help_text="Communication (attestation de communication)."
    )
    issued_at = serializers.DateTimeField()
    revoked = serializers.BooleanField()
    verification_url = serializers.CharField()


def my_certificate_data(row) -> dict:
    from apps.events.services.certificates import verification_url

    return {
        "id": row.pk,
        "nature": row.nature,
        "edition_code": row.edition.code,
        "edition_title_fr": row.edition.title_fr,
        "edition_title_en": row.edition.title_en or row.edition.title_fr,
        "title": row.details.get("title", ""),
        "issued_at": row.issued_at,
        "revoked": row.revoked_at is not None,
        "verification_url": verification_url(row.verification_code),
    }


class PublicVerificationSerializer(serializers.Serializer):
    """Vérification publique (K10) : ni institution, ni empreinte, ni code d'autres pièces."""

    kind = serializers.ChoiceField(choices=VERIFICATION_KIND_CHOICES)
    nature = serializers.ChoiceField(choices=DocumentNature.choices)
    name = serializers.CharField(allow_null=True, help_text="Absent si le compte est anonymisé.")
    edition_title_fr = serializers.CharField()
    edition_title_en = serializers.CharField()
    edition_start = serializers.DateField(allow_null=True)
    edition_end = serializers.DateField(allow_null=True)
    issued_at = serializers.DateTimeField()
    status = serializers.ChoiceField(choices=VERIFICATION_STATUS_CHOICES)
    revoked_at = serializers.DateTimeField(allow_null=True)
