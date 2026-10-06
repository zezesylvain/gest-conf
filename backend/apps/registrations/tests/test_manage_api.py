"""Inscriptions dans la gestion (plan L6, J1, J7, J9, J12)."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.core.actor import Actor
from apps.core.models import AuditLog
from apps.registrations.models import Registration
from apps.registrations.services import orders
from apps.registrations.tests.helpers import (
    complete_billing,
    grid,
    open_edition,
    participant_user,
    set_window,
)

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = open_edition()
    grid(
        edition, "etudiant", early_local="25000", early_international="50000", onsite_local="40000"
    )
    complete_billing(edition)
    return edition


@pytest.fixture
def finance(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/registrations"


def ordered(edition, **profile):
    return orders.place_order(
        edition, participant_user(**profile), category="etudiant", method="transfer", actor=COMMAND
    )


def test_j12_list_filters_and_search(edition, finance):
    first = ordered(edition, last_name="Kouassi")
    ordered(edition, last_name="Traoré")
    orders.cancel_by_participant(first, actor=COMMAND)
    body = finance.get(base(edition)).json()
    assert body["count"] == 2
    pending = finance.get(base(edition), {"status": "pending"}).json()["results"]
    assert [row["person"]["name"] for row in pending] == ["Awa Traoré"]
    found = finance.get(base(edition), {"q": "kouas"}).json()["results"]
    assert [row["id"] for row in found] == [first.pk]
    by_reference = finance.get(base(edition), {"q": first.reference}).json()["results"]
    assert [row["id"] for row in by_reference] == [first.pk]


def test_detail_shows_person_history_and_documents(edition, finance):
    registration = ordered(edition)
    body = finance.get(f"{base(edition)}/{registration.pk}").json()
    assert body["person"]["email"] == registration.user.email
    assert [row["to_status"] for row in body["history"]] == ["pending"]
    assert [document["kind"] for document in body["documents"]] == ["proforma"]
    assert body["refunds"] == []


def test_j7_manual_payment_by_secretariat_confirms_and_invoices(edition):
    secretariat = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    registration = ordered(edition)
    response = secretariat.post(
        f"{base(edition)}/{registration.pk}/payments",
        {
            "method": "transfer",
            "amount": "25000",
            "reference": "VIR-42",
            "received_on": timezone.localdate().isoformat(),
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["status"] == "confirmed"
    assert body["payments"][0]["provider_reference"] == "VIR-42"
    assert {document["kind"] for document in body["documents"]} == {"proforma", "invoice"}


def test_committee_registers_an_existing_account_after_closing_at_onsite_rate(edition, finance):
    """J2 : après la clôture des inscriptions en ligne, le CO inscrit au tarif « sur place »."""
    now = timezone.now()
    set_window(
        edition,
        opens=now - timezone.timedelta(days=30),
        early=now - timezone.timedelta(days=20),
        closes=now - timezone.timedelta(days=1),
    )
    user = participant_user()
    response = finance.post(
        base(edition),
        {"email": user.email.upper(), "category": "etudiant", "method": "onsite"},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert (response.json()["period"], response.json()["total"]) == ("onsite", "40000.00")
    unknown = finance.post(
        base(edition),
        {"email": "personne@example.org", "category": "etudiant", "method": "onsite"},
        format="json",
    )
    assert unknown.status_code == 400


def test_j9_cancel_with_reason_then_refund_issues_credit_note(edition, finance):
    registration = ordered(edition)
    finance.post(
        f"{base(edition)}/{registration.pk}/payments",
        {"method": "transfer", "amount": "25000", "received_on": timezone.localdate().isoformat()},
        format="json",
    )
    response = finance.post(
        f"{base(edition)}/{registration.pk}/cancel",
        {"reason": "Visa refusé", "refund_percent": 100},
        format="json",
    )
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["refund_due"]) == ("cancelled", "25000.00")
    response = finance.post(
        f"{base(edition)}/{registration.pk}/refunds",
        {
            "amount": "25000",
            "method": "Virement",
            "refunded_on": timezone.localdate().isoformat(),
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["refunds"][0]["credit_note"].startswith("AV-")
    assert AuditLog.objects.get(action="registration.cancelled").reason == "Visa refusé"


def test_j4_waiver_requires_reason(edition, finance):
    registration = ordered(edition)
    url = f"{base(edition)}/{registration.pk}/waive"
    assert finance.post(url, {"reason": ""}, format="json").status_code == 400
    response = finance.post(url, {"reason": "Intervenant invité"}, format="json")
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["method"]) == ("confirmed", "waiver")


def test_j8_issue_pending_invoices_and_list_documents(edition, finance):
    from apps.payments.models import BillingProfile

    BillingProfile.objects.filter(edition=edition).update(legal_name="")
    registration = ordered(edition)
    finance.post(
        f"{base(edition)}/{registration.pk}/payments",
        {"method": "transfer", "amount": "25000", "received_on": timezone.localdate().isoformat()},
        format="json",
    )
    documents_url = f"/v1/manage/editions/{edition.pk}/billing/documents"
    assert finance.get(documents_url, {"kind": "invoice"}).json()["count"] == 0
    issue = f"{documents_url}/issue-pending"
    assert finance.post(issue).status_code == 409
    BillingProfile.objects.filter(edition=edition).update(legal_name="Association")
    assert finance.post(issue).json() == {"issued": 1}
    rows = finance.get(documents_url, {"kind": "invoice"}).json()["results"]
    assert rows[0]["registration_reference"] == registration.reference
    assert rows[0]["customer"] == "Awa Zadi"


def test_chair_reads_but_cannot_validate_a_payment(edition):
    chair = client_for(make_member(edition, Role.CHAIR))
    registration = ordered(edition)
    assert chair.get(f"{base(edition)}/{registration.pk}").status_code == 200
    response = chair.post(
        f"{base(edition)}/{registration.pk}/payments",
        {"method": "transfer", "amount": "25000", "received_on": timezone.localdate().isoformat()},
        format="json",
    )
    assert response.status_code == 403
    assert Registration.objects.get(pk=registration.pk).status == "pending"
