"""Sérialiseurs de l'espace compte (``/v1/me…``, plan L1 §9.3)."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework import serializers

from apps.accounts.consents import CURRENT_TEXT_VERSIONS
from apps.accounts.models import BIO_MAX_LENGTH, ConsentKind, ConsentSource, ProfileTitle
from apps.accounts.roles import CAPABILITY_CHOICES, InvitableRole, OcFunction, Role
from apps.accounts.validators import validate_country, validate_orcid
from apps.conferences.models import EditionStatus


class Locale(models.TextChoices):
    """Langues de l'interface et des e-mails (nom de schéma ``Locale``)."""

    FR = "fr", "Français"
    EN = "en", "English"


class ConsentRequestSource(models.TextChoices):
    """Origines possibles d'un consentement déclaré par l'API (nom de schéma distinct :
    sous-ensemble de ``ConsentSource``, sans « command »)."""

    FIRST_LOGIN = ConsentSource.FIRST_LOGIN.value, ConsentSource.FIRST_LOGIN.label
    ACCOUNT = ConsentSource.ACCOUNT.value, ConsentSource.ACCOUNT.label


class EditionRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)
    oc_function = serializers.ChoiceField(choices=OcFunction.choices)


class MeEditionSerializer(serializers.Serializer):
    """Édition où le compte a au moins un rôle actif, avec ses capacités (§5.1) : Angular
    masque les actions d'après elles, sans recopier la matrice en TypeScript."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    year = serializers.IntegerField()
    status = serializers.ChoiceField(choices=EditionStatus.choices)
    roles = EditionRoleSerializer(many=True)
    capabilities = serializers.ListField(child=serializers.ChoiceField(choices=CAPABILITY_CHOICES))
    mfa_required = serializers.BooleanField(
        help_text="Un rôle de l'édition impose la 2FA pour les routes de gestion (D3)."
    )


class MePendingInvitationSerializer(serializers.Serializer):
    """Invitation en attente adressée à une adresse vérifiée du compte."""

    edition_code = serializers.CharField(source="edition.code")
    edition_title_fr = serializers.CharField(source="edition.title_fr")
    edition_title_en = serializers.CharField(source="edition.title_en")
    role = serializers.ChoiceField(choices=InvitableRole.choices)
    oc_function = serializers.ChoiceField(choices=OcFunction.choices)
    expires_at = serializers.DateTimeField()


class MeSerializer(serializers.Serializer):
    """Compte connecté : identité, langue, éditions (rôles, capacités), invitations en
    attente. L'état de la 2FA s'y ajoutera en L1.6."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    locale = serializers.ChoiceField(choices=Locale.choices)
    profile_complete = serializers.BooleanField(
        help_text="Nom, prénom, institution et pays renseignés."
    )
    privacy_notice_pending = serializers.BooleanField(
        help_text="Vrai tant que la version courante de la notice n'a pas été lue."
    )
    editions = MeEditionSerializer(many=True)
    pending_invitations = MePendingInvitationSerializer(many=True)


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
