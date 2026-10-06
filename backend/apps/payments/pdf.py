"""PDF des factures, avoirs et pro forma (plan L6, J8 ; bilan de L6.0 : ``fpdf2``).

Libellés bilingues (français, puis anglais), montants au format français de la devise,
police DejaVu Sans embarquée en sous-ensemble (noms hors latin-1). Date de création fixée à
la date d'émission : la sortie est identique octet pour octet pour les mêmes données, ce
qui rend l'empreinte SHA-256 vérifiable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from fpdf import FPDF
from fpdf.fonts import FontFace

from apps.core.money import format_amount, quantize

FONTS = Path(__file__).resolve().parent / "fonts"
FONT = "DejaVu"

TITLES = {
    "invoice": ("Facture", "Invoice"),
    "credit_note": ("Avoir", "Credit note"),
    "proforma": ("Facture pro forma", "Pro forma invoice"),
}


@dataclass(frozen=True, slots=True)
class DocumentData:
    kind: str
    number: str
    issued_at: datetime
    timezone: str
    edition_title: str
    registration_reference: str
    issuer: dict
    customer: dict
    lines: list[dict]
    amount: Decimal
    currency: str
    original_number: str = ""
    payment: dict = field(default_factory=dict)
    due_at: datetime | None = None


def _date(value: datetime, tz_name: str) -> str:
    return value.astimezone(ZoneInfo(tz_name)).strftime("%d/%m/%Y")


def _money(value: Decimal | str, currency: str) -> str:
    return format_amount(Decimal(value), currency, "fr")


def vat_breakdown(amount: Decimal, rate: Decimal, currency: str) -> tuple[Decimal, Decimal]:
    """Montant toutes taxes comprises → (hors taxes, TVA), arrondis à la devise."""
    net = quantize(amount * Decimal(100) / (Decimal(100) + rate), currency)
    return net, amount - net


def render(data: DocumentData) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_creation_date(data.issued_at)
    title_fr, title_en = TITLES[data.kind]
    pdf.set_title(f"{title_fr} {data.number}")
    pdf.set_author(data.issuer.get("legal_name", ""))
    pdf.set_creator("GEST-CONF")
    pdf.add_font(FONT, "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font(FONT, "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    def text(value: str, size: float = 10, style: str = "", height: float = 5) -> None:
        pdf.set_font(FONT, style, size)
        pdf.multi_cell(0, height, value, new_x="LMARGIN", new_y="NEXT")

    # Émetteur.
    text(data.issuer.get("legal_name", ""), 12, "B", 6)
    for value in (data.issuer.get("address", ""), data.issuer.get("tax_identifiers", "")):
        if value:
            text(value, 9, height=4.5)
    pdf.ln(6)
    # Titre et références.
    text(f"{title_fr} n° {data.number}", 16, "B", 8)
    text(title_en, 10, height=5)
    pdf.ln(2)
    text(f"Date d'émission / Issue date : {_date(data.issued_at, data.timezone)}", 9)
    text(f"Événement / Event : {data.edition_title}", 9)
    text(f"Inscription / Registration : {data.registration_reference}", 9)
    if data.original_number:
        text(f"Avoir sur la facture / Credit note for invoice : {data.original_number}", 9)
    pdf.ln(4)
    # Client.
    text("Client / Customer", 10, "B")
    for key in ("name", "organization", "address", "email"):
        if data.customer.get(key):
            text(data.customer[key], 9, height=4.5)
    pdf.ln(4)
    # Lignes.
    with pdf.table(
        col_widths=(140, 50),
        text_align=("LEFT", "RIGHT"),
        headings_style=FontFace(emphasis="BOLD"),
        line_height=6,
    ) as table:
        pdf.set_font(FONT, "", 9)
        heading = table.row()
        heading.cell("Désignation / Description")
        heading.cell("Montant / Amount")
        for line in data.lines:
            label = line["label_fr"]
            if line.get("label_en") and line["label_en"] != label:
                label = f"{label} / {line['label_en']}"
            row = table.row()
            row.cell(label)
            row.cell(_money(line["amount"], data.currency))
    pdf.ln(3)
    pdf.set_font(FONT, "B", 11)
    rate = data.issuer.get("vat_rate")
    if rate is not None:
        net, vat = vat_breakdown(data.amount, Decimal(rate), data.currency)
        pdf.set_font(FONT, "", 10)
        pdf.cell(0, 6, f"Total HT / Net : {_money(net, data.currency)}", align="R")
        pdf.ln(6)
        pdf.cell(0, 6, f"TVA / VAT ({rate} %) : {_money(vat, data.currency)}", align="R")
        pdf.ln(6)
        pdf.set_font(FONT, "B", 11)
        pdf.cell(0, 7, f"Total TTC / Total : {_money(data.amount, data.currency)}", align="R")
    else:
        pdf.cell(0, 7, f"Total : {_money(data.amount, data.currency)}", align="R")
    pdf.ln(9)
    if rate is None and data.issuer.get("vat_note"):
        text(data.issuer["vat_note"], 9)
    # Mentions propres à la nature de la pièce.
    if data.kind == "invoice" and data.payment:
        text(
            "Facture acquittée / Paid on "
            f"{data.payment['date']} ({data.payment['method']}, {data.payment['reference']})",
            9,
        )
    if data.kind == "proforma":
        text("Document non comptable : il ne vaut pas facture.", 9, "B")
        text("Not an invoice: for payment purposes only.", 9)
        if data.due_at is not None:
            text(f"À régler avant le / Payable before : {_date(data.due_at, data.timezone)}", 9)
        if data.issuer.get("bank_details"):
            pdf.ln(2)
            text("Coordonnées bancaires / Bank details", 9, "B")
            text(data.issuer["bank_details"], 9, height=4.5)
        text(f"Référence à rappeler / Reference : {data.registration_reference}", 9)
    if data.issuer.get("footer"):
        pdf.ln(6)
        text(data.issuer["footer"], 8, height=4)
    return bytes(pdf.output())
