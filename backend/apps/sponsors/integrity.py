"""Contrôles d'intégrité des partenaires (``check_integrity``, plan L8, N17)."""

from __future__ import annotations


def check_contributions() -> list[str]:
    """Une contribution « reçue » porte un montant et une date (ligne du budget)."""
    from django.db.models import Q

    from apps.sponsors.models import Sponsor, SponsorStatus

    rows = Sponsor.objects.filter(status=SponsorStatus.RECEIVED).filter(
        Q(received_amount__isnull=True) | Q(received_amount=0) | Q(received_on__isnull=True)
    )
    return [
        f"partenaire {pk} : reçu sans montant ni date" for pk in rows.values_list("pk", flat=True)
    ]
