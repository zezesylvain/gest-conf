"""Suivi financier d'une édition (plan L6, J12) : tableau de bord et exports comptables.

Montants dans la devise de l'édition, en ``Decimal``. Les exports (paiements, pièces) sont
des exports de masse : journalisés (RG-17), avec réauthentification récente (vue, J1).
"""

from __future__ import annotations

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db.models import Count, Q, Sum
from django.utils.translation import gettext as _

from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.spreadsheet import csv_text
from apps.payments.models import BillingDocument, DocumentKind, Payment, PaymentStatus, Refund
from apps.payments.services.documents import pending_invoices
from apps.registrations.models import (
    PaymentMethod,
    Registration,
    RegistrationCategory,
    RegistrationStatus,
)
from apps.registrations.services.settings import registration_settings

ZERO = Decimal(0)


def _sum(queryset, field: str = "amount") -> Decimal:
    return queryset.aggregate(total=Sum(field))["total"] or ZERO


def dashboard(edition: Edition) -> dict:
    """Recettes (paiements réussis), remboursements, impayés (commandes en attente),
    répartition par moyen et par catégorie, pièces émises, points à traiter."""
    registrations = Registration.objects.filter(edition=edition)
    statuses = dict(
        registrations.values_list("status")
        .annotate(count=Count("id"))
        .values_list("status", "count")
    )
    payments = Payment.objects.filter(registration__edition=edition, status=PaymentStatus.SUCCEEDED)
    collected = _sum(payments)
    refunded = _sum(Refund.objects.filter(registration__edition=edition))
    by_method = [
        {"method": row["method"], "count": row["count"], "amount": row["amount"] or ZERO}
        for row in payments.values("method")
        .annotate(count=Count("id"), amount=Sum("amount"))
        .order_by("method")
    ]
    categories = RegistrationCategory.objects.filter(edition=edition).annotate(
        confirmed=Count(
            "registrations", filter=Q(registrations__status=RegistrationStatus.CONFIRMED)
        ),
        amount=Sum(
            "registrations__total",
            filter=Q(registrations__status=RegistrationStatus.CONFIRMED),
        ),
    )
    documents = BillingDocument.objects.filter(edition=edition)
    refunds_due = _sum(
        registrations.filter(status=RegistrationStatus.CANCELLED, refund_due__isnull=False),
        "refund_due",
    )
    orphans = payments.exclude(registration__status=RegistrationStatus.CONFIRMED).count()
    return {
        "currency": registration_settings(edition).currency,
        "registrations": {status: statuses.get(status, 0) for status in RegistrationStatus.values},
        "collected": collected,
        "refunded": refunded,
        "net": collected - refunded,
        "outstanding": _sum(registrations.filter(status=RegistrationStatus.PENDING), "total"),
        "refunds_due": max(refunds_due - refunded, ZERO),
        "by_method": by_method,
        "by_category": [
            {
                "code": category.code,
                "label_fr": category.label_fr,
                "label_en": category.label_en,
                "confirmed": category.confirmed,
                "amount": category.amount or ZERO,
            }
            for category in categories.order_by("position", "id")
        ],
        "invoices": {
            "count": documents.filter(kind=DocumentKind.INVOICE).count(),
            "amount": _sum(documents.filter(kind=DocumentKind.INVOICE)),
        },
        "credit_notes": {
            "count": documents.filter(kind=DocumentKind.CREDIT_NOTE).count(),
            "amount": _sum(documents.filter(kind=DocumentKind.CREDIT_NOTE)),
        },
        "pending_invoices": pending_invoices(edition).count(),
        "orphan_payments": orphans,
        "waivers": registrations.filter(
            method=PaymentMethod.WAIVER, status=RegistrationStatus.CONFIRMED
        ).count(),
    }


def net_collected(edition: Edition) -> Decimal:
    """Encaissé net de l'édition : paiements réussis moins remboursements (réalisé de la
    ligne « inscriptions » du budget, plan L8, N4)."""
    collected = _sum(
        Payment.objects.filter(registration__edition=edition, status=PaymentStatus.SUCCEEDED)
    )
    return collected - _sum(Refund.objects.filter(registration__edition=edition))


def _local(edition: Edition):
    zone = ZoneInfo(edition.timezone)

    def convert(value) -> str:
        return value.astimezone(zone).strftime("%Y-%m-%d %H:%M") if value else ""

    return convert


def export_payments(edition: Edition, rows, *, actor: Actor) -> str:
    local = _local(edition)
    rows = list(rows)
    content = csv_text(
        [
            _("Référence"),
            _("Inscription"),
            _("Participant"),
            _("Fournisseur"),
            _("Moyen"),
            _("Référence du fournisseur"),
            _("Montant"),
            _("Devise"),
            _("Statut"),
            _("Créé le"),
            _("Terminé le"),
            _("Reçu le"),
        ],
        (
            [
                payment.reference,
                payment.registration.reference,
                payment.registration.billing_name,
                payment.provider,
                payment.method,
                payment.provider_reference,
                payment.amount,
                payment.currency,
                payment.status,
                local(payment.created_at),
                local(payment.completed_at),
                payment.received_on.isoformat() if payment.received_on else "",
            ]
            for payment in rows
        ),
    )
    record("billing.payments_exported", actor=actor, edition=edition, after={"count": len(rows)})
    return content


def export_documents(edition: Edition, rows, *, actor: Actor) -> str:
    local = _local(edition)
    rows = list(rows)
    content = csv_text(
        [
            _("Numéro"),
            _("Nature"),
            _("Facture d'origine"),
            _("Inscription"),
            _("Client"),
            _("Organisme"),
            _("Montant"),
            _("Devise"),
            _("Émise le"),
        ],
        (
            [
                document.number,
                document.kind,
                document.original.number if document.original_id else "",
                document.registration.reference,
                document.customer.get("name", ""),
                document.customer.get("organization", ""),
                document.amount,
                document.currency,
                local(document.issued_at),
            ]
            for document in rows
        ),
    )
    record("billing.documents_exported", actor=actor, edition=edition, after={"count": len(rows)})
    return content
