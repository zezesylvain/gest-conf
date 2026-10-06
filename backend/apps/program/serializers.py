"""Sérialiseurs du programme (plan L5 §4). Les réponses publiques et « Mon passage » (L5.4)
sont construites par liste blanche depuis l'instantané publié, jamais depuis le brouillon."""

from __future__ import annotations

from rest_framework import serializers

from apps.conferences.models import Edition


class ProgramSettingsSerializer(serializers.ModelSerializer):
    """Paramètres du programme de l'édition (I17) : tampon entre créneaux (RG-13) et RG-11,
    sans effet avant le lot L6."""

    class Meta:
        model = Edition
        fields = ("session_buffer_minutes", "presenter_registration_required")
