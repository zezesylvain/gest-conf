"""Sérialiseurs des inscriptions (plan L6 §4). Montants : chaînes décimales (``Decimal``),
jamais des flottants ; ils sont calculés par le serveur seul."""

from __future__ import annotations

from rest_framework import serializers

from apps.registrations.models import RegistrationSettings

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
