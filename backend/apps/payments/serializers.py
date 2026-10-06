"""Sérialiseurs des paiements et de la facturation (plan L6 §4)."""

from __future__ import annotations

from rest_framework import serializers

from apps.core.money import DECIMAL_PLACES, MAX_DIGITS, Currency
from apps.payments.models import MANUAL_METHOD_CHOICES, BillingProfile, DocumentKind


class BillingProfileSerializer(serializers.ModelSerializer):
    """Mentions de facturation (J8, Q8) : lecture ``finance.read``, écriture
    ``pricing.write`` avec réauthentification récente (J1). ``is_complete`` : raison sociale
    et adresse renseignées, sans quoi aucune facture ne s'émet."""

    is_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = BillingProfile
        fields = (
            "legal_name",
            "address",
            "tax_identifiers",
            "vat_rate",
            "vat_note",
            "footer",
            "bank_details",
            "invoice_prefix",
            "credit_note_prefix",
            "proforma_prefix",
            "is_complete",
        )


class ManualPaymentSerializer(serializers.Serializer):
    """Paiement reçu hors ligne (J7) : virement ou sur place, montant égal au total."""

    method = serializers.ChoiceField(choices=MANUAL_METHOD_CHOICES)
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    received_on = serializers.DateField()
    note = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class RefundSerializer(serializers.Serializer):
    """Remboursement fait hors plateforme (J9) ; l'avoir est émis sur la facture."""

    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    method = serializers.CharField(max_length=64)
    reference = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    refunded_on = serializers.DateField()


class BillingDocumentSerializer(serializers.Serializer):
    """Pièce de facturation (gestion, ``finance.read``)."""

    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=DocumentKind.choices)
    number = serializers.CharField()
    registration_id = serializers.IntegerField()
    registration_reference = serializers.CharField()
    customer = serializers.CharField()
    original = serializers.CharField(allow_null=True)
    amount = serializers.DecimalField(max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES)
    currency = serializers.ChoiceField(choices=Currency.choices)
    issued_at = serializers.DateTimeField()


class IssuedCountSerializer(serializers.Serializer):
    issued = serializers.IntegerField()
