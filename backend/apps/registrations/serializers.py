"""Sérialiseurs des inscriptions (plan L6 §4). Montants : chaînes décimales (``Decimal``),
jamais des flottants ; ils sont calculés par le serveur seul."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.money import DECIMAL_PLACES, MAX_DIGITS, Currency
from apps.payments.models import DocumentKind
from apps.registrations.models import (
    ORDER_METHOD_CHOICES,
    LineKind,
    PaymentMethod,
    Period,
    PromoCode,
    RegistrationCategory,
    RegistrationOption,
    RegistrationSettings,
    RegistrationStatus,
    Zone,
)

PERIODS = [Period.EARLY, Period.REGULAR, Period.ONSITE]

# --- Gestion (plan L6 §4) ---------------------------------------------------------------------


class RegistrationSettingsSerializer(serializers.ModelSerializer):
    """Paramètres des inscriptions (J2, J5, J9) : lecture ``registrations.read``, écriture
    ``pricing.write``."""

    local_countries = serializers.ListField(
        child=serializers.CharField(max_length=2), required=False
    )

    class Meta:
        model = RegistrationSettings
        fields = (
            "currency",
            "local_countries",
            "online_enabled",
            "transfer_enabled",
            "onsite_enabled",
            "online_deadline_hours",
            "transfer_deadline_days",
            "cancellation_deadline",
            "refund_percent_before",
            "refund_percent_after",
        )


class FeeSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=Period.choices)
    zone = serializers.ChoiceField(choices=Zone.choices)
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)


class FeeGridSerializer(serializers.Serializer):
    """Grille complète d'une catégorie (une cellule par période et zone proposées)."""

    fees = FeeSerializer(many=True)


class CategorySerializer(serializers.ModelSerializer):
    """Catégorie et sa grille de tarifs (gestion). ``code`` : fixé à la création."""

    fees = serializers.SerializerMethodField()
    in_use = serializers.SerializerMethodField()

    class Meta:
        model = RegistrationCategory
        fields = (
            "id",
            "code",
            "label_fr",
            "label_en",
            "description_fr",
            "description_en",
            "requires_proof",
            "is_active",
            "position",
            "fees",
            "in_use",
        )
        read_only_fields = ("id",)

    @extend_schema_field(FeeSerializer(many=True))
    def get_fees(self, category: RegistrationCategory) -> list[dict]:
        return FeeSerializer(
            sorted(category.fees.all(), key=lambda fee: (PERIODS.index(fee.period), fee.zone)),
            many=True,
        ).data

    def get_in_use(self, category: RegistrationCategory) -> bool:
        return bool(getattr(category, "registration_count", 0))


class OptionSerializer(serializers.ModelSerializer):
    """Option à quota (gestion) : ``reserved`` places tenues par les inscriptions en attente
    ou confirmées ; ``categories`` : codes des catégories autorisées (vide : toutes)."""

    categories = serializers.SlugRelatedField(
        slug_field="code", many=True, required=False, queryset=RegistrationCategory.objects.all()
    )

    class Meta:
        model = RegistrationOption
        fields = (
            "id",
            "code",
            "label_fr",
            "label_en",
            "description_fr",
            "description_en",
            "price_local",
            "price_international",
            "quota",
            "reserved",
            "categories",
            "is_active",
            "position",
        )
        read_only_fields = ("id", "reserved")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edition = self.context.get("edition")
        if edition is not None:
            self.fields["categories"].child_relation.queryset = RegistrationCategory.objects.filter(
                edition=edition
            )

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        if "categories" in values:
            values["categories"] = [category.code for category in values["categories"]]
        return values


class PromoCodeSerializer(serializers.ModelSerializer):
    """Code promo (gestion) : utilisations réservées (commandes en attente) et consommées
    (inscriptions confirmées)."""

    categories = serializers.SlugRelatedField(
        slug_field="code", many=True, required=False, queryset=RegistrationCategory.objects.all()
    )

    class Meta:
        model = PromoCode
        fields = (
            "id",
            "code",
            "kind",
            "value",
            "scope",
            "categories",
            "max_uses",
            "reserved_uses",
            "consumed_uses",
            "valid_until",
            "is_active",
        )
        read_only_fields = ("id", "reserved_uses", "consumed_uses")
        # Unicité contrôlée par le service, après normalisation en majuscules.
        validators = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edition = self.context.get("edition")
        if edition is not None:
            self.fields["categories"].child_relation.queryset = RegistrationCategory.objects.filter(
                edition=edition
            )

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        if "categories" in values:
            values["categories"] = [category.code for category in values["categories"]]
        return values


# --- Public et participant (plan L6 §4) -------------------------------------------------------


class PublicFeeSerializer(FeeSerializer):
    pass


class PublicCategorySerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()
    description_fr = serializers.CharField()
    description_en = serializers.CharField()
    requires_proof = serializers.BooleanField()
    fees = PublicFeeSerializer(many=True)


class PublicOptionSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()
    description_fr = serializers.CharField()
    description_en = serializers.CharField()
    price_local = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    price_international = serializers.DecimalField(
        max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES
    )
    limited = serializers.BooleanField(help_text="Places limitées (quota).")
    categories = serializers.ListField(child=serializers.CharField())


class PublicRegistrationSerializer(serializers.Serializer):
    """Page publique « Inscription » (J13), lue au build du portail : catégories et tarifs,
    options, dates clés (UTC), moyens de paiement proposés, pays « locaux ». Ni quota
    restant ni donnée personnelle."""

    currency = serializers.ChoiceField(choices=Currency.choices)
    timezone = serializers.CharField()
    opens_at = serializers.DateTimeField(allow_null=True)
    early_bird_end = serializers.DateTimeField(allow_null=True)
    closes_at = serializers.DateTimeField(allow_null=True)
    methods = serializers.ListField(child=serializers.ChoiceField(choices=PaymentMethod.choices))
    local_countries = serializers.ListField(child=serializers.CharField())
    categories = PublicCategorySerializer(many=True)
    options = PublicOptionSerializer(many=True)


class QuoteRequestSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=32)
    options = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, default=list, max_length=20
    )
    promo_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class LineSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=LineKind.choices)
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)


class QuoteSerializer(serializers.Serializer):
    """Prix calculé par le serveur, sans engagement (aucune place ni code réservés)."""

    category = serializers.CharField()
    period = serializers.ChoiceField(choices=Period.choices)
    zone = serializers.ChoiceField(choices=Zone.choices)
    currency = serializers.ChoiceField(choices=Currency.choices)
    lines = LineSerializer(many=True)
    total = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)


# --- Inscriptions : participant et gestion (plan L6 §4) --------------------------------------


class RegistrationEditionSerializer(serializers.Serializer):
    code = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    timezone = serializers.CharField()


class CategoryRefSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()
    requires_proof = serializers.BooleanField()


class DocumentRefSerializer(serializers.Serializer):
    """Pièce de facturation de l'inscription (le PDF se télécharge à part)."""

    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=DocumentKind.choices)
    number = serializers.CharField()
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    currency = serializers.ChoiceField(choices=Currency.choices)
    issued_at = serializers.DateTimeField()


class PaymentRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    provider = serializers.CharField()
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    reference = serializers.CharField()
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    currency = serializers.ChoiceField(choices=Currency.choices)
    status = serializers.CharField()
    completed_at = serializers.DateTimeField(allow_null=True)


class ProofSerializer(serializers.Serializer):
    name = serializers.CharField()
    kind = serializers.CharField()
    size = serializers.IntegerField()
    uploaded_at = serializers.DateTimeField()


def proof_data(registration) -> dict | None:
    if not registration.proof_storage_name:
        return None
    return {
        "name": registration.proof_original_name,
        "kind": registration.proof_kind,
        "size": registration.proof_size,
        "uploaded_at": registration.proof_uploaded_at,
    }


def registration_data(registration) -> dict:
    """Champs communs à l'espace du participant et à la gestion (lignes figées, documents,
    paiements). Le jeton QR n'est jamais renvoyé : le QR se télécharge à part."""
    edition = registration.edition
    category = registration.category
    return {
        "id": registration.pk,
        "reference": registration.reference,
        "edition": {
            "code": edition.code,
            "title_fr": edition.title_fr,
            "title_en": edition.title_en,
            "timezone": edition.timezone,
        },
        "category": {
            "code": category.code,
            "label_fr": category.label_fr,
            "label_en": category.label_en,
            "requires_proof": category.requires_proof,
        },
        "status": registration.status,
        "period": registration.period,
        "zone": registration.zone,
        "method": registration.method,
        "lines": registration.lines,
        "total": registration.total,
        "currency": registration.currency,
        "due_at": registration.due_at,
        "confirmed_at": registration.confirmed_at,
        "closed_at": registration.closed_at,
        "refund_due": registration.refund_due,
        "billing_name": registration.billing_name,
        "billing_organization": registration.billing_organization,
        "billing_address": registration.billing_address,
        "proof": proof_data(registration),
        "has_qr": bool(registration.qr_token),
        "documents": [
            {
                "id": document.pk,
                "kind": document.kind,
                "number": document.number,
                "amount": document.amount,
                "currency": document.currency,
                "issued_at": document.issued_at,
            }
            for document in sorted(
                registration.billing_documents.all(), key=lambda item: (item.issued_at, item.pk)
            )
        ],
        "payments": [
            {
                "id": payment.pk,
                "provider": payment.provider,
                "method": payment.method,
                "reference": payment.reference,
                "amount": payment.amount,
                "currency": payment.currency,
                "status": payment.status,
                "completed_at": payment.completed_at,
            }
            for payment in sorted(
                registration.payments.all(), key=lambda item: (item.created_at, item.pk)
            )
        ],
        "created_at": registration.created_at,
    }


class RegistrationSerializer(serializers.Serializer):
    """Inscription vue par son titulaire (« Mon inscription », J13) ou par le CO."""

    id = serializers.IntegerField()
    reference = serializers.CharField()
    edition = RegistrationEditionSerializer()
    category = CategoryRefSerializer()
    status = serializers.ChoiceField(choices=RegistrationStatus.choices)
    period = serializers.ChoiceField(choices=Period.choices)
    zone = serializers.ChoiceField(choices=Zone.choices)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    lines = LineSerializer(many=True)
    total = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    currency = serializers.ChoiceField(choices=Currency.choices)
    due_at = serializers.DateTimeField(allow_null=True)
    confirmed_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    refund_due = serializers.DecimalField(
        max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, allow_null=True
    )
    billing_name = serializers.CharField()
    billing_organization = serializers.CharField()
    billing_address = serializers.CharField()
    proof = ProofSerializer(allow_null=True)
    has_qr = serializers.BooleanField()
    documents = DocumentRefSerializer(many=True)
    payments = PaymentRefSerializer(many=True)
    created_at = serializers.DateTimeField()


class MyRegistrationSerializer(RegistrationSerializer):
    """Ajoute ce que le participant peut faire : annuler (et la part remboursée), demander
    une pro forma."""

    can_cancel = serializers.BooleanField()
    refund_percent = serializers.IntegerField(allow_null=True)
    cancellation_deadline = serializers.DateTimeField(allow_null=True)


class OrderSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=32)
    options = serializers.ListField(
        child=serializers.CharField(max_length=32), required=False, default=list, max_length=20
    )
    promo_code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    method = serializers.ChoiceField(choices=ORDER_METHOD_CHOICES)
    billing_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    billing_organization = serializers.CharField(max_length=255, required=False, allow_blank=True)
    billing_address = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class BillingIdentitySerializer(serializers.Serializer):
    billing_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    billing_organization = serializers.CharField(max_length=255, required=False, allow_blank=True)
    billing_address = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ProofUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class ManageOrderSerializer(OrderSerializer):
    """Inscription saisie par le CO pour un compte existant (après la clôture : tarif
    « sur place », J2)."""

    email = serializers.EmailField()


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)
    refund_percent = serializers.IntegerField(
        min_value=0, max_value=100, required=False, allow_null=True
    )


class WaiverSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)


class RegistrantSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    country = serializers.CharField()


class ManageRegistrationListSerializer(serializers.Serializer):
    """Ligne de la liste des inscriptions (gestion, ``registrations.read``)."""

    id = serializers.IntegerField()
    reference = serializers.CharField()
    person = RegistrantSerializer()
    category = CategoryRefSerializer()
    status = serializers.ChoiceField(choices=RegistrationStatus.choices)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    total = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    currency = serializers.ChoiceField(choices=Currency.choices)
    due_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    confirmed_at = serializers.DateTimeField(allow_null=True)
    has_proof = serializers.BooleanField()
    has_invoice = serializers.BooleanField()


class HistorySerializer(serializers.Serializer):
    from_status = serializers.CharField()
    to_status = serializers.ChoiceField(choices=RegistrationStatus.choices)
    at = serializers.DateTimeField()
    actor = serializers.CharField()
    reason = serializers.CharField()


class ManagePaymentSerializer(PaymentRefSerializer):
    provider_reference = serializers.CharField()
    received_on = serializers.DateField(allow_null=True)
    recorded_by = serializers.CharField()
    note = serializers.CharField()


class RefundRefSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    method = serializers.CharField()
    reference = serializers.CharField()
    refunded_on = serializers.DateField()
    credit_note = serializers.CharField(allow_null=True)


class ManageRegistrationSerializer(RegistrationSerializer):
    """Détail d'une inscription (gestion) : personne, historique, paiements complets,
    remboursements."""

    person = RegistrantSerializer()
    history = HistorySerializer(many=True)
    payments = ManagePaymentSerializer(many=True)
    refunds = RefundRefSerializer(many=True)
