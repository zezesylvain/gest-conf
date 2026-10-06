"""Données personnelles des paiements et de la facturation (registre
``apps.core.personal_data``, RG-18 ; plan L6, J14).

- **Export** : paiements, factures, avoirs, pro forma et remboursements des inscriptions de
  la personne (montants, références, dates ; jamais d'empreinte de jeton).
- **Anonymisation** : les **factures et avoirs sont conservés** avec l'identité figée à leur
  émission (obligation légale de conservation des pièces comptables, J14) ; leur nombre est
  consigné au journal (« billing.documents_retained »), sans donnée personnelle. Paiements et
  remboursements ne portent pas d'identité (seulement des références).
"""

from __future__ import annotations

from typing import Any

from apps.core.audit import record
from apps.core.personal_data import AnonymizationContext, register_personal_data
from apps.payments.models import BillingDocument, DocumentKind, Payment, Refund


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    payments = (
        Payment.objects.filter(registration__user=user)
        .select_related("registration__edition")
        .order_by("created_at", "id")
    )
    documents = (
        BillingDocument.objects.filter(registration__user=user)
        .select_related("edition")
        .order_by("issued_at", "id")
    )
    refunds = (
        Refund.objects.filter(registration__user=user)
        .select_related("registration__edition")
        .order_by("refunded_on", "id")
    )
    return {
        "payments": [
            {
                "edition": row.registration.edition.code,
                "provider": row.provider,
                "method": row.method,
                "reference": row.reference,
                "amount": str(row.amount),
                "currency": row.currency,
                "status": row.status,
                "created_at": _iso(row.created_at),
                "completed_at": _iso(row.completed_at),
            }
            for row in payments
        ],
        "billing_documents": [
            {
                "edition": row.edition.code,
                "kind": row.kind,
                "number": row.number,
                "amount": str(row.amount),
                "currency": row.currency,
                "customer": row.customer,
                "issued_at": _iso(row.issued_at),
            }
            for row in documents
        ],
        "refunds": [
            {
                "edition": row.registration.edition.code,
                "amount": str(row.amount),
                "currency": row.currency,
                "method": row.method,
                "refunded_on": _iso(row.refunded_on),
            }
            for row in refunds
        ],
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    retained = BillingDocument.objects.filter(
        registration__user=user, kind__in=(DocumentKind.INVOICE, DocumentKind.CREDIT_NOTE)
    ).count()
    if retained:
        record(
            "billing.documents_retained",
            actor=context.actor,
            obj=user,
            after={"documents": retained},
            reason="J14",
        )


def register_payments_personal_data() -> None:
    # Les clés vers User de ces modèles désignent le membre du CO qui a validé, émis ou
    # enregistré (trace de gestion) ; la personne inscrite est rattachée par son inscription.
    register_personal_data(
        "payments.payments",
        models=("payments.Payment", "payments.BillingDocument", "payments.Refund"),
        export=_export,
        anonymize=_anonymize,
        rank=480,
    )
