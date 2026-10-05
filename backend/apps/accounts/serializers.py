"""Sérialiseurs de l'espace compte (``/v1/me…``, plan L1 §9.3)."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework import serializers

from apps.accounts.consents import CURRENT_TEXT_VERSIONS
from apps.accounts.models import BIO_MAX_LENGTH, ConsentKind, ConsentSource, ProfileTitle
from apps.accounts.validators import validate_country, validate_orcid


class Locale(models.TextChoices):
    """Langues de l'interface et des e-mails (nom de schéma ``Locale``)."""

    FR = "fr", "Français"
    EN = "en", "English"


class ConsentRequestSource(models.TextChoices):
    """Origines possibles d'un consentement déclaré par l'API (nom de schéma distinct :
    sous-ensemble de ``ConsentSource``, sans « command »)."""

    FIRST_LOGIN = ConsentSource.FIRST_LOGIN.value, ConsentSource.FIRST_LOGIN.label
    ACCOUNT = ConsentSource.ACCOUNT.value, ConsentSource.ACCOUNT.label


class MeSerializer(serializers.Serializer):
    """Compte connecté. Rôles, capacités, invitations (L1.5) et état 2FA (L1.6) s'y ajouteront."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    locale = serializers.ChoiceField(choices=Locale.choices)
    profile_complete = serializers.BooleanField(
        help_text="Nom, prénom, institution et pays renseignés."
    )
    privacy_notice_pending = serializers.BooleanField(
        help_text="Vrai tant que la version courante de la notice n'a pas été lue."
    )


class PreferencesSerializer(serializers.Serializer):
    locale = serializers.ChoiceField(choices=Locale.choices)


class ProfileSerializer(serializers.Serializer):
    title = serializers.ChoiceField(choices=ProfileTitle.choices, required=False, allow_blank=True)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    institution = serializers.CharField(max_length=255, required=False, allow_blank=True)
    department = serializers.CharField(max_length=255, required=False, allow_blank=True)
    country = serializers.CharField(
        max_length=2,
        required=False,
        allow_blank=True,
        help_text="Code ISO 3166-1 alpha-2 (« CI », « FR »...), majuscules ou minuscules.",
    )
    orcid = serializers.CharField(
        max_length=19,
        required=False,
        allow_blank=True,
        help_text="Forme 0000-0000-0000-000X, clé de contrôle vérifiée.",
    )
    bio = serializers.CharField(
        max_length=BIO_MAX_LENGTH,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        help_text="Texte brut.",
    )
    is_complete = serializers.BooleanField(read_only=True)

    # Normalisation (majuscules) avant contrôle ; Django ValidationError → erreur de champ.
    def validate_country(self, value: str) -> str:
        value = value.upper()
        _run_django_validator(validate_country, value)
        return value

    def validate_orcid(self, value: str) -> str:
        value = value.upper()
        _run_django_validator(validate_orcid, value)
        return value


def _run_django_validator(validator, value: str) -> None:
    try:
        validator(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(exc.messages) from exc


class ConsentStateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ConsentKind.choices)
    granted = serializers.BooleanField()
    text_version = serializers.CharField(allow_blank=True)
    recorded_at = serializers.DateTimeField(allow_null=True)
    current_text_version = serializers.CharField()


class ConsentRecordSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ConsentKind.choices)
    granted = serializers.BooleanField()
    text_version = serializers.CharField()
    recorded_at = serializers.DateTimeField()
    source = serializers.ChoiceField(choices=ConsentSource.choices)


class ConsentsSerializer(serializers.Serializer):
    states = ConsentStateSerializer(many=True)
    history = ConsentRecordSerializer(many=True)


class ConsentCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ConsentKind.choices)
    granted = serializers.BooleanField()
    # Écran d'accueil de la première connexion ou espace compte.
    source = serializers.ChoiceField(
        choices=ConsentRequestSource.choices, default=ConsentRequestSource.ACCOUNT
    )


def consent_states(states: dict) -> list[dict]:
    return [
        {
            "kind": kind,
            "granted": bool(consent and consent.granted),
            "text_version": consent.text_version if consent else "",
            "recorded_at": consent.recorded_at if consent else None,
            "current_text_version": CURRENT_TEXT_VERSIONS[kind],
        }
        for kind, consent in states.items()
    ]
