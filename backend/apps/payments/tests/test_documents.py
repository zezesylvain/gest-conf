"""Factures, avoirs et pro forma (plan L6, J8, J9 ; RG-14) : PDF, numérotation, intégrité."""

from __future__ import annotations

import hashlib
import io
from decimal import Decimal

import pytest
from django.utils import timezone
from pypdf import PdfReader

from apps.core.actor import Actor
from apps.core.money import NARROW_NBSP as THIN
from apps.core.money import NBSP
from apps.payments import integrity, pdf
from apps.payments.models import BillingDocument
from apps.payments.services import documents, manual
from apps.registrations.services import orders
from apps.registrations.tests.helpers import complete_billing, grid, open_edition, participant_user

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = open_edition()
    grid(edition, "etudiant", early_local="25000", early_international="50000")
    complete_billing(edition, tax_identifiers="RCCM CI-ABJ-2026-B-1 · NCC 1234567X")
    return edition


def paid_registration(edition, **profile):
    user = participant_user(**profile)
    registration = orders.place_order(
        edition, user, category="etudiant", method="transfer", actor=COMMAND
    )
    manual.record_manual_payment(
        registration,
        method="transfer",
        amount=registration.total,
        reference="VIR-2027-001",
        received_on=timezone.localdate(),
        actor=COMMAND,
    )
    registration.refresh_from_db()
    return registration


def text_of(document: BillingDocument) -> str:
    data = documents.read_document(document)
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def test_rg14_invoice_pdf_carries_issuer_customer_lines_and_paid_mention(edition):
    registration = paid_registration(edition, first_name="Nguyễn Thị", last_name="Ánh")
    invoice = BillingDocument.objects.get(registration=registration, kind="invoice")
    text = text_of(invoice)
    assert f"Facture n° {invoice.number}" in text
    assert "Association GEST-CONF" in text and "RCCM CI-ABJ-2026-B-1" in text
    assert "Nguyễn Thị Ánh" in text
    assert f"25{THIN}000{NBSP}F CFA" in text
    assert "Facture acquittée" in text and "VIR-2027-001" in text
    assert hashlib.sha256(documents.read_document(invoice)).hexdigest() == invoice.sha256


def test_proforma_pdf_is_not_an_invoice_and_gives_bank_details(edition):
    user = participant_user()
    registration = orders.place_order(
        edition, user, category="etudiant", method="transfer", actor=COMMAND
    )
    proforma = BillingDocument.objects.get(registration=registration, kind="proforma")
    text = text_of(proforma)
    assert "Facture pro forma" in text
    assert "Document non comptable" in text
    assert "IBAN CI00 0000 0000" in text
    assert registration.reference in text


def test_j9_credit_note_references_its_invoice(edition):
    registration = paid_registration(edition)
    orders.cancel_by_committee(registration, reason="Annulé", percent=50, actor=COMMAND)
    refund = manual.record_refund(
        registration,
        amount=Decimal("12500"),
        method="Mobile money",
        reference="",
        refunded_on=timezone.localdate(),
        actor=COMMAND,
    )
    invoice = BillingDocument.objects.get(registration=registration, kind="invoice")
    text = text_of(refund.credit_note)
    assert f"Avoir n° {refund.credit_note.number}" in text
    assert invoice.number in text
    assert f"12{THIN}500{NBSP}F CFA" in text


def test_vat_breakdown_from_total_including_tax(edition):
    assert pdf.vat_breakdown(Decimal("11800"), Decimal("18"), "XOF") == (
        Decimal("10000"),
        Decimal("1800"),
    )
    complete_billing(edition, vat_rate=Decimal("18"))
    invoice = BillingDocument.objects.get(registration=paid_registration(edition), kind="invoice")
    text = text_of(invoice)
    assert "TVA / VAT (18.00 %)" in text and "Total TTC" in text


def test_rg14_series_are_gap_free_per_kind_and_year(edition):
    first, second = paid_registration(edition), paid_registration(edition)
    numbers = [
        BillingDocument.objects.get(registration=item, kind="invoice").sequence
        for item in (first, second)
    ]
    assert numbers == [1, 2]
    assert integrity.check_series() == []
    BillingDocument.objects.filter(registration=second, kind="invoice")._unchecked_update(
        sequence=5
    )
    assert integrity.check_series()


def test_rg14_integrity_detects_modified_file(edition):
    invoice = BillingDocument.objects.get(registration=paid_registration(edition), kind="invoice")
    assert integrity.check_files() == []
    documents.DOCUMENTS.path(invoice.storage_name).write_bytes(b"%PDF-1.7 falsifie")
    assert integrity.check_files() == [f"pièce {invoice.number} : empreinte modifiée"]


def test_documents_are_append_only(edition):
    from apps.core.models import AppendOnlyError

    invoice = BillingDocument.objects.get(registration=paid_registration(edition), kind="invoice")
    invoice.amount = Decimal("1")
    with pytest.raises(AppendOnlyError):
        invoice.save()
    with pytest.raises(AppendOnlyError):
        invoice.delete()


def test_pdf_identical_for_identical_data():
    data = pdf.DocumentData(
        kind="invoice",
        number="F-GC27-2027-00001",
        issued_at=timezone.now(),
        timezone="Africa/Abidjan",
        edition_title="GEST-CONF 2027",
        registration_reference="GC27-I00001",
        issuer={"legal_name": "Association", "address": "Abidjan", "vat_rate": None},
        customer={"name": "Awa Zadi"},
        lines=[{"label_fr": "Étudiant", "label_en": "Student", "amount": "25000"}],
        amount=Decimal("25000"),
        currency="XOF",
    )
    assert pdf.render(data) == pdf.render(data)
