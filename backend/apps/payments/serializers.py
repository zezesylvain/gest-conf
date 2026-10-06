"""Sérialiseurs des paiements et de la facturation (plan L6 §4)."""

from __future__ import annotations

from rest_framework import serializers

from apps.payments.models import BillingProfile


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
