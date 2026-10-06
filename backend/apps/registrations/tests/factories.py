"""Fabriques de test des inscriptions (plan L6)."""

from __future__ import annotations

import secrets
from decimal import Decimal

from django.utils import timezone

from apps.registrations.models import (
    ACTIVE_STATUSES,
    Period,
    Registration,
    RegistrationCategory,
    RegistrationStatus,
    Zone,
)


def make_category(edition, code: str = "participant", **fields) -> RegistrationCategory:
    fields.setdefault("label_fr", code.capitalize())
    return RegistrationCategory.objects.create(edition=edition, code=code, **fields)


def make_registration(
    edition, user, *, status: str = RegistrationStatus.PENDING, category=None, **fields
) -> Registration:
    """Inscription posée directement (le workflow arrive en L6.3), cohérente avec les
    contraintes : clé active si en attente ou confirmée, jeton QR si confirmée."""
    category = category or make_category(edition, f"cat-{secrets.token_hex(3)}")
    active = status in ACTIVE_STATUSES
    fields.setdefault("period", Period.EARLY)
    fields.setdefault("zone", Zone.LOCAL)
    fields.setdefault("method", "transfer")
    fields.setdefault("total", Decimal("25000"))
    fields.setdefault("currency", "XOF")
    fields.setdefault(
        "lines",
        [{"kind": "registration", "code": category.code, "label_fr": "x", "amount": "25000"}],
    )
    if status == RegistrationStatus.CONFIRMED:
        fields.setdefault("qr_token", secrets.token_urlsafe(24))
        fields.setdefault("confirmed_at", timezone.now())
    return Registration.objects.create(
        edition=edition,
        user=user,
        category=category,
        status=status,
        active_key=Registration.make_active_key(edition.pk, user.pk) if active else None,
        **fields,
    )
