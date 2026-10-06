"""Catalogue de test des inscriptions (plan L6) : dates clés, catégories et tarifs."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.utils import timezone

from apps.conferences.models import EditionStatus, KeyDate
from apps.conferences.tests.factories import EditionFactory
from apps.registrations.models import Fee, RegistrationCategory, RegistrationOption

NOW = dt.datetime(2027, 3, 1, 12, tzinfo=dt.UTC)


def set_window(edition, *, opens=None, early=None, closes=None) -> None:
    for code, at in (
        ("registration_open", opens),
        ("early_bird_end", early),
        ("registration_close", closes),
    ):
        KeyDate.objects.filter(edition=edition, code=code).delete()
        if at is not None:
            KeyDate.objects.create(edition=edition, code=code, at=at)


def open_edition(**fields):
    """Édition publiée, inscriptions ouvertes depuis hier, tarif préférentiel pour dix jours."""
    edition = EditionFactory(status=EditionStatus.PUBLISHED, country="CI", **fields)
    now = timezone.now()
    set_window(
        edition,
        opens=now - dt.timedelta(days=1),
        early=now + dt.timedelta(days=10),
        closes=now + dt.timedelta(days=40),
    )
    return edition


def grid(edition, code: str = "etudiant", **amounts) -> RegistrationCategory:
    """Catégorie et sa grille ; ``amounts`` : ``early_local=25000``, etc."""
    category = RegistrationCategory.objects.create(
        edition=edition, code=code, label_fr=code.capitalize(), label_en=f"{code} (EN)"
    )
    for key, amount in amounts.items():
        period, zone = key.split("_")
        Fee.objects.create(category=category, period=period, zone=zone, amount=Decimal(amount))
    return category


def option(edition, code: str = "diner", **fields) -> RegistrationOption:
    fields.setdefault("label_fr", code.capitalize())
    fields.setdefault("price_local", Decimal("10000"))
    fields.setdefault("price_international", Decimal("20000"))
    return RegistrationOption.objects.create(edition=edition, code=code, **fields)
