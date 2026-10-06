"""Mentions de facturation de l'édition (plan L6, J8, Q8)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog
from apps.payments.models import BillingDocument
from apps.registrations.tests.factories import make_registration

pytestmark = pytest.mark.django_db


def url(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/billing/profile"


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def finance(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))


def test_j8_empty_profile_is_incomplete_no_invoice_until_filled(edition, finance):
    """J8 : tant que raison sociale et adresse manquent, aucune facture ne s'émet."""
    body = finance.get(url(edition)).json()
    assert body["is_complete"] is False
    assert (body["invoice_prefix"], body["credit_note_prefix"], body["proforma_prefix"]) == (
        "F",
        "AV",
        "PF",
    )
    response = finance.patch(
        url(edition),
        {"legal_name": "Association GEST-CONF", "address": "Abidjan, Côte d'Ivoire"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["is_complete"] is True
    log = AuditLog.objects.get(action="billing.profile_changed")
    assert log.after == {"legal_name": "Association GEST-CONF", "address": "Abidjan, Côte d'Ivoire"}


def test_chair_reads_but_cannot_write(edition):
    client = client_for(make_member(edition, Role.CHAIR))
    assert client.get(url(edition)).status_code == 200
    assert client.patch(url(edition), {"legal_name": "X"}, format="json").status_code == 403


def test_vat_rate_range(edition, finance):
    assert finance.patch(url(edition), {"vat_rate": "101"}, format="json").status_code == 400
    response = finance.patch(url(edition), {"vat_rate": "18.00"}, format="json")
    assert response.status_code == 200
    assert response.json()["vat_rate"] == "18.00"


@pytest.mark.parametrize("prefix", ["", "f-", "1F", "ABCDEFGHI"])
def test_prefixes_capitals_and_digits(edition, finance, prefix):
    response = finance.patch(url(edition), {"invoice_prefix": prefix}, format="json")
    assert response.status_code == 400
    assert "invoice_prefix" in response.json()["fields"]


def test_prefix_lowercase_is_normalized(edition, finance):
    response = finance.patch(url(edition), {"invoice_prefix": "fac"}, format="json")
    assert response.json()["invoice_prefix"] == "FAC"


def test_prefixes_distinct_between_series(edition, finance):
    """Le numéro affiché est unique par édition : deux séries ne partagent pas un préfixe."""
    response = finance.patch(url(edition), {"proforma_prefix": "F"}, format="json")
    assert response.status_code == 400
    assert "proforma_prefix" in response.json()["fields"]


def test_rg14_prefix_frozen_once_a_document_of_the_series_exists(edition, finance):
    """RG-14 : la série reste continue ; son préfixe ne change plus après la première pièce."""
    registration = make_registration(edition, VerifiedUserFactory())
    BillingDocument.objects.create(
        edition=edition,
        kind="invoice",
        year=2027,
        sequence=1,
        number="F2027-00001",
        registration=registration,
        amount=Decimal("25000"),
        currency="XOF",
        storage_name="x" * 32,
        sha256="0" * 64,
        size=1,
        issued_at=timezone.now(),
    )
    response = finance.patch(url(edition), {"invoice_prefix": "FA"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "setting_frozen"
    # Les autres séries restent modifiables.
    assert finance.patch(url(edition), {"proforma_prefix": "BC"}, format="json").status_code == 200
