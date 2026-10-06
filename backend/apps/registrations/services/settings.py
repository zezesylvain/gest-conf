"""Paramètres des inscriptions d'une édition (plan L6, J2, J5, J9)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.accounts.validators import validate_country
from apps.conferences.models import Edition
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.money import is_exact
from apps.registrations.models import (
    Fee,
    Registration,
    RegistrationOption,
    RegistrationSettings,
    Zone,
)

SETTINGS_FIELDS = tuple(RegistrationSettings.AUDIT_FIELDS)


def registration_settings(edition: Edition, *, lock: bool = False) -> RegistrationSettings:
    """Paramètres de l'édition, créés avec les valeurs par défaut à la première lecture."""
    manager = RegistrationSettings.objects
    if lock:
        manager = manager.select_for_update()
    found = manager.filter(edition=edition).first()
    if found is not None:
        return found
    try:
        with transaction.atomic():
            RegistrationSettings.objects.create(edition=edition)
    except IntegrityError:
        pass  # créés en parallèle
    return manager.get(edition=edition)


def local_countries(edition: Edition, settings: RegistrationSettings) -> frozenset[str]:
    """Pays « locaux » (J2) : la liste paramétrée, sinon le pays de l'édition."""
    if settings.local_countries:
        return frozenset(settings.local_countries)
    return frozenset({edition.country}) if edition.country else frozenset()


def zone_for(edition: Edition, settings: RegistrationSettings, country: str) -> str:
    return (
        Zone.LOCAL
        if country and country in local_countries(edition, settings)
        else (Zone.INTERNATIONAL)
    )


def _validate_countries(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise Invalid(fields={"local_countries": [_("Liste de codes pays attendue.")]})
    codes = sorted({item.strip().upper() for item in value if item.strip()})
    for code in codes:
        try:
            validate_country(code)
        except ValidationError as exc:
            raise Invalid(fields={"local_countries": exc.messages}) from exc
    return codes


def _check_currency_change(edition: Edition, currency: str) -> None:
    """La devise est figée dès la première inscription ; avant, les montants déjà saisis
    doivent respecter les décimales de la nouvelle devise (XOF : aucune)."""
    if Registration.objects.filter(edition=edition).exists():
        raise RuleViolation(
            _("Devise figée : des inscriptions existent déjà."),
            code=ErrorCode.SETTING_FROZEN,
            fields={"currency": [_("Devise figée : des inscriptions existent déjà.")]},
        )
    amounts = [
        *Fee.objects.filter(category__edition=edition).values_list("amount", flat=True),
        *RegistrationOption.objects.filter(edition=edition).values_list("price_local", flat=True),
        *RegistrationOption.objects.filter(edition=edition).values_list(
            "price_international", flat=True
        ),
    ]
    if any(not is_exact(amount, currency) for amount in amounts):
        raise Invalid(
            fields={
                "currency": [
                    _("Des tarifs ont plus de décimales que cette devise : corrigez-les d'abord.")
                ]
            }
        )


@transaction.atomic
def update_registration_settings(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor
) -> RegistrationSettings:
    """Écrit les paramètres (``pricing.write``), journalisés avec l'avant et l'après."""
    unknown = set(data) - set(SETTINGS_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)
    settings = registration_settings(edition, lock=True)
    values = dict(data)
    if "local_countries" in values:
        values["local_countries"] = _validate_countries(values["local_countries"])
    changed = [name for name, value in values.items() if getattr(settings, name) != value]
    if not changed:
        return settings
    if "currency" in changed:
        _check_currency_change(edition, values["currency"])
    before = snapshot(settings)
    for name in changed:
        setattr(settings, name, values[name])
    try:
        settings.full_clean(exclude=["edition"])
    except ValidationError as exc:
        raise Invalid(fields=exc.message_dict) from exc
    settings.save(update_fields=[*changed, "updated_at"])
    after = snapshot(settings)
    record(
        "registrations.settings_changed",
        actor=actor,
        edition=edition,
        obj=settings,
        before={name: before[name] for name in changed},
        after={name: after[name] for name in changed},
    )
    return settings
