"""Cycle de vie des inscriptions (plan L6, J5, J7, J9, J11) : commande, confirmation,
annulation, expiration, gratuité ; service unique des statuts (règle n° 4)."""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.tests.factories import VerifiedUserFactory
from apps.communications.models import OutboxEmail
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.payments.models import BillingDocument, Payment
from apps.payments.services import manual
from apps.registrations import workflow
from apps.registrations.models import (
    PromoCode,
    Registration,
    RegistrationOption,
    RegistrationStatus,
    RegistrationStatusHistory,
)
from apps.registrations.services import orders
from apps.registrations.services.settings import registration_settings
from apps.registrations.tests.helpers import (
    complete_billing,
    grid,
    open_edition,
    option,
    participant_user,
)

pytestmark = pytest.mark.django_db

S = RegistrationStatus
COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = open_edition()
    grid(edition, "etudiant", early_local="25000", early_international="50000")
    grid(edition, "invite", early_local="0")
    option(edition, "diner", quota=1)
    return edition


def order(edition, user=None, **fields):
    user = user or participant_user()
    fields.setdefault("category", "etudiant")
    fields.setdefault("method", "transfer")
    return orders.place_order(edition, user, actor=Actor(kind="user", user=user), **fields)


def test_j5_order_freezes_price_reserves_and_sets_due_date(edition):
    PromoCode.objects.create(edition=edition, code="ETU", kind="percent", value=Decimal("10"))
    registration = order(edition, options=["diner"], promo_code="etu")
    assert registration.status == S.PENDING
    assert registration.total == Decimal("25000") + Decimal("10000") - Decimal("2500")
    assert registration.billing_name == "Awa Zadi"
    assert RegistrationOption.objects.get(code="diner").reserved == 1
    assert PromoCode.objects.get(code="ETU").reserved_uses == 1
    # Virement : 30 jours, sans dépasser la veille de la conférence.
    assert registration.due_at > timezone.now() + dt.timedelta(days=29)
    history = RegistrationStatusHistory.objects.get(registration=registration)
    assert (history.from_status, history.to_status) == ("", S.PENDING)
    assert OutboxEmail.objects.filter(template_code="registrations/email/ordered").count() == 1


def test_j13_emails_link_to_my_registration_not_to_account_signup(edition):
    """J13 : le lien mène à « Mon inscription » (`/compte/mon-inscription`) ; `/compte/inscription`
    est la création de compte (L1)."""
    order(edition)
    email = OutboxEmail.objects.get(template_code="registrations/email/ordered")
    assert "/compte/mon-inscription" in email.body_text
    assert "/compte/inscription" not in email.body_text


def test_j5_one_active_registration_per_person(edition):
    user = participant_user()
    order(edition, user)
    with pytest.raises(RuleViolation) as error:
        order(edition, user)
    assert error.value.code == ErrorCode.ALREADY_REGISTERED


def test_j5_zero_total_is_confirmed_at_once_with_qr(edition):
    registration = order(edition, category="invite", method="online")
    assert registration.status == S.CONFIRMED
    assert registration.method == "free"
    assert len(registration.qr_token) >= 32
    assert registration.due_at is None
    assert OutboxEmail.objects.filter(template_code="registrations/email/confirmed").exists()


def test_j6_method_must_be_offered(edition):
    """Paiement en ligne désactivé par défaut tant qu'aucun fournisseur n'est configuré."""
    with pytest.raises(Invalid) as error:
        order(edition, method="online")
    assert "method" in error.value.fields


def test_j5_due_date_capped_at_conference_eve(edition):
    edition.start_date = (timezone.now() + dt.timedelta(days=5)).date()
    edition.end_date = edition.start_date + dt.timedelta(days=2)
    edition.save()
    registration = order(edition)
    assert registration.due_at <= orders._local_midnight(edition.start_date, edition.timezone)


def test_closed_registration_refused_for_participant(edition):
    from apps.registrations.tests.helpers import set_window

    set_window(edition)
    with pytest.raises(RuleViolation) as error:
        order(edition)
    assert error.value.code == ErrorCode.REGISTRATION_CLOSED


def test_j3_quota_full_refuses_second_order(edition):
    order(edition, options=["diner"])
    with pytest.raises(RuleViolation) as error:
        order(edition, options=["diner"])
    assert error.value.code == ErrorCode.OPTION_FULL
    assert Registration.objects.count() == 1


# --- Paiement manuel (J7) et facture (J8) --------------------------------------------------


def test_j7_manual_payment_confirms_and_issues_invoice(edition):
    complete_billing(edition)
    registration = order(edition, options=["diner"])
    staff = VerifiedUserFactory()
    payment = manual.record_manual_payment(
        registration,
        method="transfer",
        amount=Decimal("35000"),
        reference="VIR-123",
        received_on=timezone.localdate(),
        actor=Actor(kind="user", user=staff),
    )
    registration.refresh_from_db()
    assert registration.status == S.CONFIRMED and registration.qr_token
    assert payment.recorded_by == staff and payment.status == "succeeded"
    invoice = BillingDocument.objects.get(registration=registration, kind="invoice")
    year = timezone.localtime(invoice.issued_at).year
    assert invoice.number == f"F-{edition.code}-{year}-00001"
    assert invoice.amount == Decimal("35000")
    assert invoice.customer["name"] == "Awa Zadi"
    # La pro forma émise à la commande a sa propre série.
    proforma = BillingDocument.objects.get(registration=registration, kind="proforma")
    assert proforma.number == f"PF-{edition.code}-{year}-00001"
    assert AuditLog.objects.filter(action="payment.recorded").exists()


def test_j7_partial_payment_refused(edition):
    registration = order(edition)
    with pytest.raises(Invalid) as error:
        manual.record_manual_payment(
            registration,
            method="transfer",
            amount=Decimal("20000"),
            reference="",
            received_on=timezone.localdate(),
            actor=COMMAND,
        )
    assert "amount" in error.value.fields
    assert not Payment.objects.exists()


def test_j8_no_invoice_without_billing_details_then_issued_later(edition):
    from apps.payments.services import documents

    registration = order(edition)
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="",
        received_on=timezone.localdate(),
        actor=COMMAND,
    )
    assert not BillingDocument.objects.exists()
    assert list(documents.pending_invoices(edition)) == [registration]
    complete_billing(edition)
    assert documents.issue_pending_invoices(edition, actor=COMMAND) == 1
    assert documents.issue_pending_invoices(edition, actor=COMMAND) == 0


# --- Annulation et remboursement (J9) ------------------------------------------------------


def paid(edition, **fields):
    complete_billing(edition)
    registration = order(edition, **fields)
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="VIR",
        received_on=timezone.localdate(),
        actor=COMMAND,
    )
    registration.refresh_from_db()
    return registration


def test_j9_participant_cancels_pending_order_and_places_are_released(edition):
    PromoCode.objects.create(edition=edition, code="ETU", kind="amount", value=Decimal("1000"))
    registration = order(edition, options=["diner"], promo_code="ETU")
    orders.cancel_by_participant(registration, actor=COMMAND)
    registration.refresh_from_db()
    assert registration.status == S.CANCELLED and registration.active_key is None
    assert RegistrationOption.objects.get(code="diner").reserved == 0
    assert PromoCode.objects.get(code="ETU").reserved_uses == 0
    # Une nouvelle inscription redevient possible.
    order(edition, registration.user)


def test_j9_confirmed_cancellation_needs_deadline(edition):
    registration = paid(edition)
    with pytest.raises(RuleViolation) as error:
        orders.cancel_by_participant(registration, actor=COMMAND)
    assert error.value.code == ErrorCode.DEADLINE_PASSED
    settings_row = registration_settings(edition)
    settings_row.cancellation_deadline = timezone.now() + dt.timedelta(days=3)
    settings_row.refund_percent_before = 80
    settings_row.save()
    orders.cancel_by_participant(registration, actor=COMMAND)
    registration.refresh_from_db()
    assert registration.status == S.CANCELLED and registration.qr_token is None
    assert registration.refund_due == Decimal("20000")


def test_j9_refund_recorded_issues_credit_note(edition):
    registration = paid(edition)
    orders.cancel_by_committee(registration, reason="Visa refusé", percent=100, actor=COMMAND)
    registration.refresh_from_db()
    assert registration.refund_due == Decimal("25000")
    staff = VerifiedUserFactory()
    refund = manual.record_refund(
        registration,
        amount=Decimal("25000"),
        method="Virement",
        reference="RB-1",
        refunded_on=timezone.localdate(),
        actor=Actor(kind="user", user=staff),
    )
    credit = refund.credit_note
    invoice = BillingDocument.objects.get(registration=registration, kind="invoice")
    assert credit.kind == "credit_note" and credit.original == invoice
    assert credit.number.startswith(f"AV-{edition.code}-")
    # Jamais plus que le facturé.
    with pytest.raises(Invalid):
        manual.record_refund(
            registration,
            amount=Decimal("1"),
            method="Virement",
            reference="",
            refunded_on=timezone.localdate(),
            actor=COMMAND,
        )


def test_j9_committee_cancellation_requires_reason(edition):
    with pytest.raises(Invalid):
        orders.cancel_by_committee(order(edition), reason=" ", actor=COMMAND)


# --- Expiration (J5) et gratuité (J4) ------------------------------------------------------


def test_j5_overdue_orders_expire_once(edition):
    late = order(edition, options=["diner"])
    Registration.objects.filter(pk=late.pk).update(due_at=timezone.now() - dt.timedelta(hours=1))
    fresh = order(edition)
    assert orders.expire_overdue() == 1
    assert orders.expire_overdue() == 0
    late.refresh_from_db()
    fresh.refresh_from_db()
    assert (late.status, fresh.status) == (S.EXPIRED, S.PENDING)
    assert RegistrationOption.objects.get(code="diner").reserved == 0
    assert OutboxEmail.objects.filter(template_code="registrations/email/expired").count() == 1


def test_j4_waiver_confirms_with_zero_total_and_reason(edition):
    registration = order(edition)
    orders.grant_waiver(registration, reason="Intervenant invité", actor=COMMAND)
    registration.refresh_from_db()
    assert (registration.status, registration.total, registration.method) == (
        S.CONFIRMED,
        Decimal("0"),
        "waiver",
    )
    assert registration.lines[-1]["code"] == "WAIVER"
    assert AuditLog.objects.get(action="registration.waived").reason == "Intervenant invité"


def test_illegal_transition_is_refused(edition):
    registration = order(edition)
    workflow.transition(registration, S.EXPIRED, actor=COMMAND)
    with pytest.raises(RuleViolation) as error:
        workflow.transition(registration, S.CONFIRMED, actor=COMMAND)
    assert error.value.code == ErrorCode.INVALID_TRANSITION


def test_registration_status_is_written_only_by_the_workflow():
    """Règle n° 4 transposée (J5) : aucun module hors ``registrations/workflow.py`` n'écrit
    le statut d'une inscription."""
    apps_dir = Path(settings.BASE_DIR) / "apps"
    pattern = re.compile(
        r"\.status\s*=(?!=)|\b(?:update|create|update_or_create|get_or_create)\([^)]*\bstatus\s*="
    )
    assert pattern.search("registration.status = S.CONFIRMED")
    assert not pattern.search("Registration.objects.filter(status=S.PENDING)")
    offenders = []
    for path in apps_dir.rglob("*.py"):
        relative = path.relative_to(apps_dir).as_posix()
        if "/tests/" in relative or "/migrations/" in relative:
            continue
        if relative == "registrations/workflow.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Registration" not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and "registration" in line.lower():
                offenders.append(f"{relative}:{number}: {line.strip()}")
    assert offenders == []
