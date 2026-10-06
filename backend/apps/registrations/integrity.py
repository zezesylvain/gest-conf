"""Contrôles d'intégrité des inscriptions (plan L6 §3), lancés par ``check_integrity``."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q

from apps.registrations.models import (
    ACTIVE_STATUSES,
    PaymentMethod,
    PromoCode,
    Registration,
    RegistrationOption,
    RegistrationStatus,
)


def check_totals() -> list[str]:
    """Total = somme des lignes figées ; inscription confirmée payée, offerte ou gratuite."""
    problems = []
    rows = Registration.objects.only("pk", "lines", "total", "status", "method")
    for registration in rows.iterator(chunk_size=500):
        lines = sum((Decimal(line["amount"]) for line in registration.lines), Decimal(0))
        if lines != registration.total:
            problems.append(f"inscription {registration.pk} : total différent de ses lignes")
    unpaid = (
        Registration.objects.filter(status=RegistrationStatus.CONFIRMED, total__gt=0)
        .exclude(method__in=(PaymentMethod.FREE, PaymentMethod.WAIVER))
        .exclude(payments__status="succeeded")
    )
    for pk in unpaid.values_list("pk", flat=True):
        problems.append(f"inscription {pk} : confirmée sans paiement réussi")
    return problems


def check_reservations() -> list[str]:
    """Places réservées = inscriptions actives qui ont l'option ; utilisations réservées =
    commandes en attente avec le code ; consommées = inscriptions confirmées un jour."""
    problems = []
    options = RegistrationOption.objects.annotate(
        held=Count("registrations", filter=Q(registrations__status__in=ACTIVE_STATUSES))
    )
    for option in options:
        if option.held != option.reserved:
            problems.append(f"option {option.pk} : places réservées incohérentes")
    codes = PromoCode.objects.annotate(
        pending=Count("registrations", filter=Q(registrations__status=RegistrationStatus.PENDING)),
        consumed=Count("registrations", filter=Q(registrations__confirmed_at__isnull=False)),
    )
    for code in codes:
        if (code.pending, code.consumed) != (code.reserved_uses, code.consumed_uses):
            problems.append(f"code promo {code.pk} : utilisations incohérentes")
    return problems
