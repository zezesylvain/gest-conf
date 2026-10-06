"""« Mon inscription » : API du participant (plan L6, J5, J7, J9, J11, J13)."""

from __future__ import annotations

import hashlib
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.roles_helpers import client_for
from apps.conferences.models import Conference
from apps.core.actor import Actor
from apps.payments.models import BillingDocument
from apps.payments.services import manual
from apps.registrations.models import Registration
from apps.registrations.tests.helpers import complete_billing, grid, open_edition, participant_user

pytestmark = pytest.mark.django_db

BASE = "/v1/registrations"
PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n"


@pytest.fixture
def edition():
    edition = open_edition()
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    student = grid(edition, "etudiant", early_local="25000", early_international="50000")
    student.requires_proof = True
    student.save()
    grid(edition, "participant", early_local="40000")
    return edition


@pytest.fixture
def user():
    return participant_user()


def order(client, **fields):
    fields.setdefault("category", "etudiant")
    fields.setdefault("method", "transfer")
    return client.post(BASE, fields, format="json")


def test_j13_order_returns_frozen_lines_due_date_and_proforma(edition, user):
    complete_billing(edition)
    client = client_for(user)
    response = order(client, billing_organization="Université Félix Houphouët-Boigny")
    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["status"], body["method"], body["total"]) == ("pending", "transfer", "25000.00")
    assert body["reference"].startswith(f"{edition.code}-I")
    assert body["lines"][0]["code"] == "etudiant"
    assert body["due_at"] and body["can_cancel"] is True and body["has_qr"] is False
    assert body["billing_organization"] == "Université Félix Houphouët-Boigny"
    assert [document["kind"] for document in body["documents"]] == ["proforma"]
    assert client.get(BASE).json()[0]["id"] == body["id"]


def test_order_twice_is_409(edition, user):
    client = client_for(user)
    assert order(client).status_code == 201
    response = order(client)
    assert response.status_code == 409
    assert response.json()["code"] == "already_registered"


def test_order_requires_authentication(edition):
    assert order(APIClient()).status_code == 401


def test_someone_else_registration_is_404(edition, user):
    registration_id = order(client_for(user)).json()["id"]
    stranger = client_for(participant_user())
    for path in ("", "/cancel", "/qr", "/proforma"):
        method = stranger.get if path in ("", "/qr") else stranger.post
        assert method(f"{BASE}/{registration_id}{path}").status_code == 404


def test_billing_identity_editable_until_invoice(edition, user):
    complete_billing(edition)
    client = client_for(user)
    registration_id = order(client).json()["id"]
    response = client.patch(
        f"{BASE}/{registration_id}", {"billing_address": "BP 123, Abidjan"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["billing_address"] == "BP 123, Abidjan"
    registration = Registration.objects.get(pk=registration_id)
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="VIR",
        received_on=timezone.localdate(),
        actor=Actor.command("cli:test"),
    )
    response = client.patch(f"{BASE}/{registration_id}", {"billing_name": "X"}, format="json")
    assert response.status_code == 409


def test_j9_cancel_pending_order(edition, user):
    client = client_for(user)
    registration_id = order(client).json()["id"]
    response = client.post(f"{BASE}/{registration_id}/cancel")
    assert response.status_code == 200
    assert (response.json()["status"], response.json()["can_cancel"]) == ("cancelled", False)


def test_j2_proof_checked_by_content(edition, user):
    client = client_for(user)
    registration_id = order(client).json()["id"]
    url = f"{BASE}/{registration_id}/proof"
    fake = client.post(url, {"file": _upload("carte.pdf", b"pas un pdf")}, format="multipart")
    assert fake.status_code == 400
    response = client.post(url, {"file": _upload("carte.pdf", PDF)}, format="multipart")
    assert response.status_code == 200, response.content
    assert response.json()["proof"]["kind"] == "pdf"
    assert response.json()["proof"]["name"] == "carte.pdf"


def test_proof_refused_when_category_does_not_require_it(edition, user):
    client = client_for(user)
    registration_id = order(client, category="participant").json()["id"]
    response = client.post(
        f"{BASE}/{registration_id}/proof", {"file": _upload("x.pdf", PDF)}, format="multipart"
    )
    assert response.status_code == 400


def test_j11_qr_only_once_confirmed(edition, user):
    client = client_for(user)
    registration_id = order(client).json()["id"]
    assert client.get(f"{BASE}/{registration_id}/qr").status_code == 404
    registration = Registration.objects.get(pk=registration_id)
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="",
        received_on=timezone.localdate(),
        actor=Actor.command("cli:test"),
    )
    response = client.get(f"{BASE}/{registration_id}/qr")
    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml"
    assert response.content.startswith(b"<svg")
    registration.refresh_from_db()
    # Le jeton n'apparaît jamais dans les réponses JSON.
    assert registration.qr_token not in client.get(f"{BASE}/{registration_id}").content.decode()


def test_j8_invoice_downloaded_by_its_holder_only(edition, user):
    complete_billing(edition)
    client = client_for(user)
    registration_id = order(client).json()["id"]
    registration = Registration.objects.get(pk=registration_id)
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="",
        received_on=timezone.localdate(),
        actor=Actor.command("cli:test"),
    )
    invoice = BillingDocument.objects.get(registration=registration, kind="invoice")
    url = f"{BASE}/{registration_id}/documents/{invoice.pk}"
    response = client.get(url)
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert hashlib.sha256(response.content).hexdigest() == invoice.sha256
    assert client_for(participant_user()).get(url).status_code == 404


def test_j7_proforma_on_request_needs_billing_details(edition, user):
    client = client_for(user)
    registration_id = order(client).json()["id"]
    assert client.post(f"{BASE}/{registration_id}/proforma").status_code == 409
    complete_billing(edition)
    response = client.post(f"{BASE}/{registration_id}/proforma")
    assert response.status_code == 201
    assert response.json()["kind"] == "proforma"
    assert Decimal(response.json()["amount"]) == Decimal("25000")


def _upload(name: str, data: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, data, content_type="application/pdf")
