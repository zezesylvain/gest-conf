"""Sérialiseurs du jour J et des attestations (plan L7 §4)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.services.invitations import display_name
from apps.events.models import Checkin, CheckinMethod, Signature
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
