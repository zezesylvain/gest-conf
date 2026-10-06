"""Contrôles d'intégrité du jour J (plan L7 §3), lancés par ``check_integrity``."""

from __future__ import annotations

from django.db.models import F

from apps.events.models import Checkin
from apps.registrations.models import RegistrationStatus


def check_checkins() -> list[str]:
    """Pointages actifs d'inscriptions qui ne sont plus confirmées (annulées après le
    pointage) : signalés, sans effet sur les attestations (RG-16 exige une inscription
    confirmée) ; pointage d'une autre édition que son inscription."""
    problems = []
    inactive = (
        Checkin.objects.filter(active_key__isnull=False)
        .exclude(registration__status=RegistrationStatus.CONFIRMED)
        .values_list("pk", "registration_id")
    )
    for pk, registration_id in inactive:
        problems.append(f"pointage {pk} : inscription {registration_id} non confirmée")
    mismatched = Checkin.objects.exclude(edition_id=F("registration__edition_id")).values_list(
        "pk", flat=True
    )
    for pk in mismatched:
        problems.append(f"pointage {pk} : édition différente de celle de l'inscription")
    return problems
