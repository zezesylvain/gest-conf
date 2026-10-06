"""Données personnelles des inscriptions et de la facturation (plan L6, J14 ; RG-18)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import RuleViolation
from apps.core.models import AuditLog
from apps.payments.models import BillingDocument, Payment
from apps.registrations.models import Registration, RegistrationStatus
from apps.registrations.tests.factories import make_registration

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")
NAME = "Zéphyrine Kpangbalo"


def _invoice(registration) -> BillingDocument:
    return BillingDocument.objects.create(
        edition=registration.edition,
        kind="invoice",
        year=2027,
        sequence=1,
        number="F2027-00001",
        registration=registration,
        amount=registration.total,
        currency=registration.currency,
        customer={"name": NAME, "address": "Abidjan"},
        storage_name="y" * 32,
        sha256="0" * 64,
        size=1,
        issued_at=timezone.now(),
    )


def test_rg18_export_contains_registrations_payments_and_documents():
    user = VerifiedUserFactory()
    registration = make_registration(
        EditionFactory(),
        user,
        status=RegistrationStatus.CONFIRMED,
        billing_name=NAME,
        billing_address="Abidjan",
    )
    Payment.objects.create(
        registration=registration,
        provider="manual",
        method="transfer",
        reference="GC-1",
        amount=Decimal("25000"),
        currency="XOF",
        status="succeeded",
        notify_token_hash="f" * 64,
    )
    _invoice(registration)
    data = export_user_data(user, actor=COMMAND)
    exported = data["registrations"][0]
    assert exported["billing_name"] == NAME
    assert exported["total"] == "25000.00"
    assert data["payments"][0]["reference"] == "GC-1"
    assert "notify_token_hash" not in data["payments"][0]
    assert data["billing_documents"][0]["number"] == "F2027-00001"
    # Le jeton QR n'est pas exporté : il sert au check-in, pas à la personne.
    assert registration.qr_token not in str(data)


@pytest.mark.parametrize("status", [RegistrationStatus.PENDING, RegistrationStatus.CONFIRMED])
def test_rg18_anonymization_refused_with_active_registration_in_open_edition(status):
    """J14 : la personne annule d'abord son inscription, ou attend l'archivage."""
    user = VerifiedUserFactory()
    edition = EditionFactory()
    make_registration(edition, user, status=status)
    with pytest.raises(RuleViolation) as error:
        anonymize_user(user, actor=COMMAND, reason="Demande")
    assert error.value.fields["roles"] == [f"registration:{edition.code}"]


def test_j14_anonymization_keeps_invoices_and_reports_them():
    """J14 : identité de facturation et jeton QR effacés de l'inscription ; factures et
    avoirs conservés avec l'identité figée (obligation légale), signalés au journal."""
    user = VerifiedUserFactory()
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    registration = make_registration(
        edition,
        user,
        status=RegistrationStatus.CONFIRMED,
        billing_name=NAME,
        billing_organization="Université test",
        billing_address="Abidjan",
    )
    _invoice(registration)
    cancelled = make_registration(
        EditionFactory(), user, status=RegistrationStatus.CANCELLED, billing_name=NAME
    )

    anonymize_user(user, actor=COMMAND, reason="Demande")

    for row in Registration.objects.filter(pk__in=[registration.pk, cancelled.pk]):
        assert (row.billing_name, row.billing_organization, row.billing_address) == ("", "", "")
        assert row.qr_token is None
    assert BillingDocument.objects.get().customer["name"] == NAME
    entry = AuditLog.objects.get(action="billing.documents_retained")
    assert entry.after == {"documents": 1}
    assert NAME not in str(entry.after)
