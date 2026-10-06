"""Factures, avoirs et pro forma (plan L6, J8, J9 ; RG-14).

- **Numérotation sans trou** par (édition, nature, année) : ``core.Counter`` incrémenté dans
  la transaction qui émet la pièce (un échec annule aussi le numéro). Numéro affiché :
  ``<préfixe>-<code de l'édition>-<année>-<rang>`` (« F-GC27-2027-00001 ») ; le code de
  l'édition le rend unique même si deux éditions facturent la même année. Année : celle de
  la date d'émission **dans le fuseau de l'édition**.
- **Pièce immuable** : mentions et identité figées, PDF hors racine web, empreinte SHA-256.
- **Aucune pièce sans mentions de facturation** (raison sociale et adresse, J8) : la facture
  d'un paiement reçu avant est émise ensuite (``issue_pending_invoices``).

Les compteurs d'une année doivent exister avant la transaction qui prend un numéro (verrous
d'intervalle de MariaDB, voir ``apps.core.counters.ensure_counter``) : ``prepare_series``,
appelé hors transaction par les vues et les commandes.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import edition_title, ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.counters import ensure_counter, next_value
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.private_files import PrivateStore
from apps.payments import pdf
from apps.payments.models import (
    BillingDocument,
    BillingProfile,
    DocumentKind,
    Payment,
    PaymentStatus,
)
from apps.payments.services.billing import billing_profile
from apps.registrations.models import PaymentMethod, Registration, RegistrationStatus

DOCUMENTS = PrivateStore("billing")
PREFIX_FIELD = {
    DocumentKind.INVOICE: "invoice_prefix",
    DocumentKind.CREDIT_NOTE: "credit_note_prefix",
    DocumentKind.PROFORMA: "proforma_prefix",
}


def issue_year(edition: Edition, at: datetime) -> int:
    return at.astimezone(ZoneInfo(edition.timezone)).year


def series_scope(edition: Edition, kind: str, year: int) -> str:
    return f"billing:{edition.pk}:{kind}:{year}"


def prepare_series(edition: Edition, at: datetime | None = None) -> None:
    """Crée hors contention les compteurs de l'année en cours (trois séries)."""
    year = issue_year(edition, at or timezone.now())
    for kind in DocumentKind.values:
        ensure_counter(series_scope(edition, kind, year))


def document_number(profile: BillingProfile, kind: str, year: int, sequence: int) -> str:
    prefix = getattr(profile, PREFIX_FIELD[kind])
    return f"{prefix}-{profile.edition.code}-{year}-{sequence:05d}"


def _issuer(profile: BillingProfile, kind: str) -> dict:
    issuer = {
        "legal_name": profile.legal_name,
        "address": profile.address,
        "tax_identifiers": profile.tax_identifiers,
        "vat_rate": str(profile.vat_rate) if profile.vat_rate is not None else None,
        "vat_note": profile.vat_note,
        "footer": profile.footer,
    }
    if kind == DocumentKind.PROFORMA:
        issuer["bank_details"] = profile.bank_details
    return issuer


def _customer(registration: Registration) -> dict:
    return {
        "name": registration.billing_name,
        "organization": registration.billing_organization,
        "address": registration.billing_address,
        "email": registration.user.email,
    }


def _missing_profile() -> RuleViolation:
    return RuleViolation(
        _("Mentions de facturation incomplètes : raison sociale et adresse d'abord."),
        code=ErrorCode.SETTING_FROZEN,
    )


def _issue(
    kind: str,
    registration: Registration,
    *,
    amount: Decimal,
    lines: list[dict],
    actor: Actor,
    payment: Payment | None = None,
    original: BillingDocument | None = None,
    payment_details: dict | None = None,
) -> BillingDocument:
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Émission hors transaction.")
    edition = registration.edition
    profile = BillingProfile.objects.select_for_update().get(pk=billing_profile(edition).pk)
    if not profile.is_complete:
        raise _missing_profile()
    now = timezone.now()
    year = issue_year(edition, now)
    sequence = next_value(series_scope(edition, kind, year))
    number = document_number(profile, kind, year, sequence)
    issuer = _issuer(profile, kind)
    customer = _customer(registration)
    content = pdf.render(
        pdf.DocumentData(
            kind=kind,
            number=number,
            issued_at=now,
            timezone=edition.timezone,
            edition_title=edition_title(edition, "fr"),
            registration_reference=registration.reference,
            issuer=issuer,
            customer=customer,
            lines=lines,
            amount=amount,
            currency=registration.currency,
            original_number=original.number if original else "",
            payment=payment_details or {},
            due_at=registration.due_at if kind == DocumentKind.PROFORMA else None,
        )
    )
    storage_name, digest = DOCUMENTS.write(content)
    document = BillingDocument.objects.create(
        edition=edition,
        kind=kind,
        year=year,
        sequence=sequence,
        number=number,
        registration=registration,
        original=original,
        payment=payment,
        amount=amount,
        currency=registration.currency,
        lines=lines,
        issuer=issuer,
        customer=customer,
        storage_name=storage_name,
        sha256=digest,
        size=len(content),
        issued_at=now,
        issued_by=actor.user,
    )
    record(
        f"billing.{kind}_issued",
        actor=actor,
        edition=edition,
        obj=document,
        after={"number": number, "amount": str(amount), "currency": registration.currency},
    )
    return document


def _method_label(method: str) -> str:
    return str(PaymentMethod(method).label) if method in PaymentMethod.values else method


@transaction.atomic
def issue_invoice(
    registration: Registration, payment: Payment, *, actor: Actor
) -> BillingDocument | None:
    """Facture d'un paiement reçu (J8), qui vaut reçu (« acquittée »). Idempotente : une
    inscription n'a qu'une facture. ``None`` sans mentions de facturation (émise ensuite)."""
    existing = BillingDocument.objects.filter(
        registration=registration, kind=DocumentKind.INVOICE
    ).first()
    if existing is not None:
        return existing
    if registration.total <= 0 or not billing_profile(registration.edition).is_complete:
        return None
    date = payment.received_on or (payment.completed_at or timezone.now()).date()
    return _issue(
        DocumentKind.INVOICE,
        registration,
        amount=registration.total,
        lines=registration.lines,
        actor=actor,
        payment=payment,
        payment_details={
            "date": date.strftime("%d/%m/%Y"),
            "method": _method_label(payment.method),
            "reference": payment.provider_reference or payment.reference,
        },
    )


@transaction.atomic
def issue_proforma(registration: Registration, *, actor: Actor) -> BillingDocument:
    """Pro forma (bon de commande) d'une inscription en attente, à régler par virement ou
    sur place (J7) : série distincte, non comptable, références bancaires."""
    ensure_editable(registration.edition)
    registration = Registration.objects.select_for_update().get(pk=registration.pk)
    if registration.status != RegistrationStatus.PENDING or registration.total <= 0:
        raise RuleViolation(
            _("Pro forma réservée à une inscription en attente de paiement."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    return _issue(
        DocumentKind.PROFORMA,
        registration,
        amount=registration.total,
        lines=registration.lines,
        actor=actor,
    )


def credited_amount(invoice: BillingDocument) -> Decimal:
    total = invoice.credit_notes.aggregate(total=Sum("amount"))["total"]
    return total or Decimal(0)


@transaction.atomic
def issue_credit_note(
    invoice: BillingDocument, amount: Decimal, *, actor: Actor
) -> BillingDocument:
    """Avoir sur une facture (J9), dans sa propre série ; la somme des avoirs ne dépasse
    jamais la facture. La facture elle-même n'est ni modifiée ni supprimée (RG-14)."""
    invoice = BillingDocument.objects.select_for_update().get(pk=invoice.pk)
    available = invoice.amount - credited_amount(invoice)
    if amount <= 0 or amount > available:
        raise Invalid(fields={"amount": [_("Montant de 0 à %(max)s.") % {"max": str(available)}]})
    registration = invoice.registration
    line = {
        "kind": "discount",
        "code": "CREDIT",
        "label_fr": f"Avoir sur la facture {invoice.number}",
        "label_en": f"Credit note for invoice {invoice.number}",
        "amount": str(amount),
    }
    return _issue(
        DocumentKind.CREDIT_NOTE,
        registration,
        amount=amount,
        lines=[line],
        actor=actor,
        original=invoice,
    )


def pending_invoices(edition: Edition):
    """Inscriptions payées sans facture (mentions absentes au moment du paiement)."""
    return (
        Registration.objects.filter(
            edition=edition,
            total__gt=0,
            payments__status=PaymentStatus.SUCCEEDED,
        )
        .exclude(billing_documents__kind=DocumentKind.INVOICE)
        .distinct()
    )


def issue_pending_invoices(edition: Edition, *, actor: Actor) -> int:
    """Émet les factures en attente, une transaction par facture."""
    if not billing_profile(edition).is_complete:
        raise _missing_profile()
    prepare_series(edition)
    count = 0
    for registration in pending_invoices(edition).select_related("edition", "user"):
        payment = (
            registration.payments.filter(status=PaymentStatus.SUCCEEDED)
            .order_by("completed_at", "id")
            .first()
        )
        if issue_invoice(registration, payment, actor=actor) is not None:
            count += 1
    return count


def read_document(document: BillingDocument) -> bytes:
    return DOCUMENTS.read(document.storage_name)


def known_documents() -> list[str]:
    return list(BillingDocument.objects.values_list("storage_name", flat=True))


def proforma_on_order(registration: Registration, actor: Actor) -> None:
    """Effet de commande (J7) : pro forma émise d'office pour un virement ou un paiement sur
    place, si les mentions de facturation sont complètes (sinon, à la demande ensuite)."""
    if registration.method not in (PaymentMethod.TRANSFER, PaymentMethod.ONSITE):
        return
    if registration.total <= 0 or not billing_profile(registration.edition).is_complete:
        return
    issue_proforma(registration, actor=actor)
