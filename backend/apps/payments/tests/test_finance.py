"""Suivi financier (plan L6, J12) : tableau de bord, paiements, exports CSV journalisés et
neutralisés contre l'injection de formules."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.core.actor import Actor
from apps.core.models import AuditLog
from apps.core.spreadsheet import cell
from apps.payments.services import manual
from apps.registrations.services import orders
from apps.registrations.tests.helpers import complete_billing, grid, open_edition, participant_user

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = open_edition()
    grid(edition, "etudiant", early_local="25000")
    grid(edition, "participant", early_local="40000")
    complete_billing(edition)
    return edition


@pytest.fixture
def finance(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))


def order(edition, category="etudiant", **profile):
    return orders.place_order(
        edition,
        participant_user(**profile),
        category=category,
        method="transfer",
        actor=COMMAND,
    )


def pay(registration):
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


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}"


def test_j12_dashboard_collected_refunded_outstanding_and_split(edition, finance):
    pay(order(edition))
    cancelled = pay(order(edition, "participant"))
    orders.cancel_by_committee(cancelled, reason="Annulé", percent=50, actor=COMMAND)
    manual.record_refund(
        cancelled,
        amount=Decimal("10000"),
        method="Virement",
        reference="",
        refunded_on=timezone.localdate(),
        actor=COMMAND,
    )
    order(edition)
    body = finance.get(f"{base(edition)}/billing/dashboard").json()
    assert body["registrations"] == {"pending": 1, "confirmed": 1, "cancelled": 1, "expired": 0}
    assert (body["collected"], body["refunded"], body["net"]) == (
        "65000.00",
        "10000.00",
        "55000.00",
    )
    assert body["outstanding"] == "25000.00"
    assert body["refunds_due"] == "10000.00"  # 50 % de 40 000, 10 000 déjà remboursés
    assert body["by_method"] == [{"method": "transfer", "count": 2, "amount": "65000.00"}]
    assert [(row["code"], row["confirmed"]) for row in body["by_category"]] == [
        ("etudiant", 1),
        ("participant", 0),
    ]
    assert body["invoices"] == {"count": 2, "amount": "65000.00"}
    assert body["credit_notes"] == {"count": 1, "amount": "10000.00"}


def test_payments_list_filters(edition, finance):
    pay(order(edition))
    order(edition)
    rows = finance.get(f"{base(edition)}/billing/payments", {"status": "succeeded"}).json()
    assert rows["count"] == 1
    assert rows["results"][0]["provider"] == "manual"


def test_csv_cells_neutralize_formulas():
    assert cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert cell("-5") == "'-5"
    assert cell("Awa") == "Awa"
    assert cell(None) == ""


def test_registration_export_is_journaled_and_neutralized(edition, finance):
    pay(order(edition, first_name="=cmd", last_name="Zadi"))
    response = finance.get(f"{base(edition)}/registrations/export", {"status": "confirmed"})
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    assert "'=cmd Zadi" in text
    entry = AuditLog.objects.get(action="registrations.exported")
    assert entry.after == {"count": 1, "filters": {"status": "confirmed"}}


def test_accounting_exports_need_recent_authentication(edition):
    member = make_member(edition, Role.OC_MEMBER, oc_function="finance")
    stale = client_for(member, recent_auth=False)
    for path in ("billing/payments/export", "billing/documents/export"):
        response = stale.get(f"{base(edition)}/{path}")
        assert response.status_code == 403
        assert response.json()["code"] == "reauthentication_required"
    pay(order(edition))
    fresh = client_for(member)
    text = fresh.get(f"{base(edition)}/billing/documents/export").content.decode()
    assert f"F-{edition.code}-" in text
    assert AuditLog.objects.filter(action="billing.documents_exported").exists()
