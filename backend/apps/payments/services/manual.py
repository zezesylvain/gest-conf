"""Paiement manuel et remboursement (plan L6, J7, J9).

- **Paiement manuel** (virement, sur place) : validé par le CO à réception, avec
  réauthentification (vue) ; montant **égal** au total (paiement partiel : P3) ; confirme
  l'inscription et émet la facture si les mentions de facturation sont complètes.
- **Remboursement** : fait hors plateforme, puis enregistré ; il émet l'avoir sur la facture.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.payments.models import (
    BillingDocument,
    DocumentKind,
    Payment,
    PaymentStatus,
    Provider,
    Refund,
)
from apps.payments.services import documents
from apps.registrations import workflow
from apps.registrations.models import PaymentMethod, Registration, RegistrationStatus

MANUAL_METHODS = (PaymentMethod.TRANSFER, PaymentMethod.ONSITE)


def next_reference(registration: Registration) -> str:
    """Notre référence de paiement (30 caractères au plus, une par tentative) :
    « <édition>-<inscription>-<rang> », sous le verrou de l'inscription."""
    rank = Payment.objects.filter(registration=registration).count() + 1
    return f"{registration.edition.code}-{registration.pk}-{rank}"


@transaction.atomic
def record_manual_payment(
    registration: Registration,
    *,
    method: str,
    amount: Decimal,
    reference: str,
    received_on: date,
    actor: Actor,
    note: str = "",
) -> Payment:
    ensure_editable(registration.edition)
    registration = (
        Registration.objects.select_for_update()
        .select_related("edition", "user")
        .get(pk=registration.pk)
    )
    if registration.status != RegistrationStatus.PENDING:
        raise RuleViolation(
            _("Seule une inscription en attente de paiement peut être réglée."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    if method not in MANUAL_METHODS:
        raise Invalid(fields={"method": [_("Virement ou paiement sur place.")]})
    if amount != registration.total:
        raise Invalid(
            fields={
                "amount": [
                    _("Montant attendu : %(total)s (paiement partiel non pris en charge).")
                    % {"total": str(registration.total)}
                ]
            }
        )
    if received_on > timezone.localdate():
        raise Invalid(fields={"received_on": [_("Date future.")]})
    payment = Payment.objects.create(
        registration=registration,
        provider=Provider.MANUAL,
        method=method,
        reference=next_reference(registration),
        provider_reference=reference.strip(),
        amount=amount,
        currency=registration.currency,
        status=PaymentStatus.SUCCEEDED,
        completed_at=timezone.now(),
        received_on=received_on,
        recorded_by=actor.user,
        note=note.strip(),
    )
    record(
        "payment.recorded",
        actor=actor,
        edition=registration.edition,
        obj=payment,
        after={
            "reference": payment.reference,
            "method": method,
            "amount": str(amount),
            "received_on": received_on.isoformat(),
        },
    )
    if registration.method != method:
        registration.method = method
        registration.save(update_fields=["method", "updated_at"])
    workflow.transition(registration, RegistrationStatus.CONFIRMED, actor=actor)
    documents.issue_invoice(registration, payment, actor=actor)
    return payment


def refunded_amount(registration: Registration) -> Decimal:
    total = registration.refunds.aggregate(total=Sum("amount"))["total"]
    return total or Decimal(0)


@transaction.atomic
def record_refund(
    registration: Registration,
    *,
    amount: Decimal,
    method: str,
    reference: str,
    refunded_on: date,
    actor: Actor,
) -> Refund:
    """Remboursement d'une inscription annulée, fait hors plateforme (J9) : avoir émis sur
    la facture (la facture doit exister) ; jamais plus que le facturé non encore crédité."""
    ensure_editable(registration.edition)
    registration = (
        Registration.objects.select_for_update()
        .select_related("edition", "user")
        .get(pk=registration.pk)
    )
    if registration.status != RegistrationStatus.CANCELLED:
        raise RuleViolation(
            _("Remboursement après annulation seulement."), code=ErrorCode.INVALID_TRANSITION
        )
    invoice = BillingDocument.objects.filter(
        registration=registration, kind=DocumentKind.INVOICE
    ).first()
    if invoice is None:
        raise RuleViolation(
            _("Émettez d'abord la facture de cette inscription."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    if refunded_on > timezone.localdate():
        raise Invalid(fields={"refunded_on": [_("Date future.")]})
    if not method.strip():
        raise Invalid(fields={"method": [_("Moyen obligatoire.")]})
    credit = documents.issue_credit_note(invoice, amount, actor=actor)
    refund = Refund.objects.create(
        registration=registration,
        credit_note=credit,
        amount=amount,
        currency=registration.currency,
        method=method.strip(),
        reference=reference.strip(),
        refunded_on=refunded_on,
        recorded_by=actor.user,
    )
    record(
        "billing.refund_recorded",
        actor=actor,
        edition=registration.edition,
        obj=refund,
        after={"amount": str(amount), "credit_note": credit.number},
    )
    return refund
