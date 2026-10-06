"""Données personnelles des inscriptions (registre ``apps.core.personal_data``, RG-18 ; plan
L6, J14).

- **Export** : inscriptions de la personne (catégorie, statut, lignes, total, moyen, identité
  de facturation) et leur historique.
- **Anonymisation** : refusée tant que la personne a une inscription en attente ou confirmée
  dans une édition non archivée (``registration_duties``) : elle l'annule d'abord, ou attend
  l'archivage. Ensuite : identité de facturation et jeton QR effacés ; l'inscription reste
  (statistiques, rattachement des factures, que ``apps.payments`` conserve, J14).
"""

from __future__ import annotations

from typing import Any

from apps.conferences.models import EditionStatus
from apps.core.personal_data import (
    AnonymizationContext,
    exempt_model,
    register_duty_check,
    register_personal_data,
)
from apps.registrations.models import ACTIVE_STATUSES, Registration


def registration_duties(user) -> list[str]:
    codes = (
        Registration.objects.filter(user=user, status__in=ACTIVE_STATUSES)
        .exclude(edition__status=EditionStatus.ARCHIVED)
        .values_list("edition__code", flat=True)
    )
    return sorted({f"registration:{code}" for code in codes})


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    rows = (
        Registration.objects.filter(user=user)
        .select_related("edition", "category")
        .prefetch_related("history")
        .order_by("created_at", "id")
    )
    return {
        "registrations": [
            {
                "edition": row.edition.code,
                "category": row.category.code,
                "status": row.status,
                "period": row.period,
                "zone": row.zone,
                "method": row.method,
                "lines": row.lines,
                "total": str(row.total),
                "currency": row.currency,
                "billing_name": row.billing_name,
                "billing_organization": row.billing_organization,
                "billing_address": row.billing_address,
                "created_at": _iso(row.created_at),
                "confirmed_at": _iso(row.confirmed_at),
                "history": [
                    {
                        "from": item.from_status,
                        "to": item.to_status,
                        "at": _iso(item.at),
                        "reason": item.reason,
                    }
                    for item in row.history.all()
                ],
            }
            for row in rows
        ]
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    Registration.objects.filter(user=user).update(
        billing_name="", billing_organization="", billing_address="", qr_token=None
    )


def register_registrations_personal_data() -> None:
    register_personal_data(
        "registrations.registrations",
        models=("registrations.Registration",),
        export=_export,
        anonymize=_anonymize,
        rank=470,
    )
    register_duty_check(registration_duties)
    exempt_model(
        "registrations.RegistrationStatusHistory",
        "actor : auteur d'un changement de statut (trace de gestion, RG-17) ; l'historique de "
        "la personne est exporté avec ses inscriptions.",
    )
