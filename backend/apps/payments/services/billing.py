"""Mentions de facturation de l'édition (plan L6, J8, Q8)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.payments.models import BillingDocument, BillingProfile, DocumentKind

PROFILE_FIELDS = tuple(BillingProfile.AUDIT_FIELDS)
PREFIX_FIELDS = {
    "invoice_prefix": DocumentKind.INVOICE,
    "credit_note_prefix": DocumentKind.CREDIT_NOTE,
    "proforma_prefix": DocumentKind.PROFORMA,
}
PREFIX_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,7}$")


def billing_profile(edition: Edition, *, lock: bool = False) -> BillingProfile:
    """Mentions de l'édition, créées vides à la première lecture."""
    manager = BillingProfile.objects
    if lock:
        manager = manager.select_for_update()
    found = manager.filter(edition=edition).first()
    if found is not None:
        return found
    try:
        with transaction.atomic():
            BillingProfile.objects.create(edition=edition)
    except IntegrityError:
        pass  # créées en parallèle
    return manager.get(edition=edition)


def _validate_prefixes(profile: BillingProfile, values: Mapping[str, Any]) -> None:
    """Préfixes : majuscules et chiffres, distincts entre séries (le numéro affiché est
    unique par édition), figés dès la première pièce de leur série."""
    errors: dict[str, list[Any]] = {}
    for name in PREFIX_FIELDS:
        if name in values and not PREFIX_PATTERN.match(values[name]):
            errors[name] = [_("Une à huit majuscules ou chiffres, en commençant par une lettre.")]
    final = {name: values.get(name, getattr(profile, name)) for name in PREFIX_FIELDS}
    if len(set(final.values())) != len(final):
        for name in PREFIX_FIELDS:
            if name in values:
                errors.setdefault(name, []).append(_("Préfixe déjà utilisé par une autre série."))
    if errors:
        raise Invalid(fields=errors)
    for name, kind in PREFIX_FIELDS.items():
        changed = name in values and values[name] != getattr(profile, name)
        if changed and BillingDocument.objects.filter(edition=profile.edition, kind=kind).exists():
            raise RuleViolation(
                _("Préfixe figé : des pièces de cette série ont déjà été émises."),
                code=ErrorCode.SETTING_FROZEN,
                fields={name: [_("Préfixe figé : des pièces de cette série existent.")]},
            )


@transaction.atomic
def update_billing_profile(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor
) -> BillingProfile:
    """Écrit les mentions (``pricing.write``, réauthentification récente, J1). Les pièces déjà
    émises gardent leurs mentions figées ; seules les suivantes changent."""
    unknown = set(data) - set(PROFILE_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)
    profile = billing_profile(edition, lock=True)
    values = {
        name: value.strip().upper() if name in PREFIX_FIELDS else value
        for name, value in data.items()
    }
    changed = [name for name, value in values.items() if getattr(profile, name) != value]
    if not changed:
        return profile
    _validate_prefixes(profile, {name: values[name] for name in changed})
    before = snapshot(profile)
    for name in changed:
        setattr(profile, name, values[name])
    try:
        profile.full_clean(exclude=["edition"])
    except ValidationError as exc:
        raise Invalid(fields=exc.message_dict) from exc
    profile.save(update_fields=[*changed, "updated_at"])
    after = snapshot(profile)
    record(
        "billing.profile_changed",
        actor=actor,
        edition=edition,
        obj=profile,
        before={name: before[name] for name in changed},
        after={name: after[name] for name in changed},
    )
    return profile
