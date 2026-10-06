"""Contraintes en base des inscriptions et des paiements (plan L6 §3). MariaDB fait foi en CI ;
SQLite applique aussi ces contraintes CHECK."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.tests.factories import EditionFactory
from apps.payments.models import BillingDocument
from apps.registrations.models import (
    Fee,
    PromoCode,
    Registration,
    RegistrationOption,
    RegistrationStatus,
)
from apps.registrations.tests.factories import make_category, make_registration

pytestmark = pytest.mark.django_db


def test_j5_one_active_registration_per_person_and_edition():
    edition = EditionFactory()
    user = VerifiedUserFactory()
    make_registration(edition, user)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_registration(edition, user)
    # Une inscription annulée ne bloque pas une nouvelle inscription.
    Registration.objects.filter(edition=edition, user=user).update(
        status=RegistrationStatus.CANCELLED, active_key=None
    )
    make_registration(edition, user)


def test_j5_active_key_only_while_pending_or_confirmed():
    registration = make_registration(EditionFactory(), VerifiedUserFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.filter(pk=registration.pk).update(status=RegistrationStatus.EXPIRED)


def test_j11_qr_token_only_on_confirmed_registration():
    registration = make_registration(EditionFactory(), VerifiedUserFactory())
    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.filter(pk=registration.pk).update(qr_token="jeton")


def test_j2_one_fee_per_category_period_zone_and_never_negative():
    category = make_category(EditionFactory())
    Fee.objects.create(category=category, period="early", zone="local", amount=Decimal("0"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Fee.objects.create(category=category, period="early", zone="local", amount=Decimal("1"))
    with pytest.raises(IntegrityError), transaction.atomic():
        Fee.objects.create(category=category, period="regular", zone="local", amount=Decimal("-1"))


def test_j3_option_reservations_within_quota():
    option = RegistrationOption.objects.create(
        edition=EditionFactory(), code="diner", label_fr="Dîner", quota=2, reserved=2
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        RegistrationOption.objects.filter(pk=option.pk).update(reserved=3)


def test_j4_promo_code_uses_within_maximum_and_percent_range():
    edition = EditionFactory()
    code = PromoCode.objects.create(
        edition=edition, code="ETU", kind="percent", value=Decimal("10"), max_uses=2
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        PromoCode.objects.filter(pk=code.pk).update(reserved_uses=2, consumed_uses=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        PromoCode.objects.create(edition=edition, code="TROP", kind="percent", value=Decimal("150"))


def test_rg14_document_number_unique_and_credit_note_has_original():
    edition = EditionFactory()
    registration = make_registration(edition, VerifiedUserFactory())
    common = {
        "edition": edition,
        "registration": registration,
        "amount": Decimal("25000"),
        "currency": "XOF",
        "storage_name": "z" * 32,
        "sha256": "0" * 64,
        "size": 1,
        "issued_at": timezone.now(),
        "year": 2027,
    }
    invoice = BillingDocument.objects.create(kind="invoice", sequence=1, number="F1", **common)
    with pytest.raises(IntegrityError), transaction.atomic():
        BillingDocument.objects.create(kind="invoice", sequence=1, number="F2", **common)
    with pytest.raises(IntegrityError), transaction.atomic():
        BillingDocument.objects.create(kind="credit_note", sequence=1, number="AV1", **common)
    with pytest.raises(IntegrityError), transaction.atomic():
        BillingDocument.objects.create(
            kind="invoice", sequence=2, number="F3", original=invoice, **common
        )
    BillingDocument.objects.create(
        kind="credit_note", sequence=1, number="AV1", original=invoice, **common
    )
