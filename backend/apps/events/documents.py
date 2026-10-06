"""PDF des attestations (et des lettres d'invitation en L7.5) : plan L7, K9, K12, K19.

Modèle officiel paramétrable : en-tête (image de l'institution) ou bandeau du titre de
l'édition, titre et texte en français puis en anglais, date d'émission, bloc de signature
(image, nom, fonction) et QR de vérification, l'un à droite et l'autre à gauche au choix,
pied de page. A4 paysage pour les attestations, A4 portrait pour les lettres.

Date de création du PDF fixée à la date d'émission : la sortie est identique octet pour
octet pour les mêmes données (avant signature PAdES, qui ajoute un horodatage).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import segno
from fpdf import FPDF

from apps.core.pdf import FONT, add_fonts

BAND_COLOR = (31, 42, 68)
MUTED = (90, 90, 90)
MONTHS_FR = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)
MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True, slots=True)
class DocumentData:
    document_title: str
    edition_title: str
    title_fr: str
    title_en: str
    body_fr: str
    body_en: str
    footer_fr: str
    footer_en: str
    issued_at: datetime
    timezone: str
    signatory_name: str
    signatory_title_fr: str
    signatory_title_en: str
    signature_png: bytes | None
    header_png: bytes | None
    verification_url: str
    signature_right: bool = True
    landscape: bool = True


def date_fr(value: datetime, tz_name: str) -> str:
    local = value.astimezone(ZoneInfo(tz_name))
    day = "1er" if local.day == 1 else str(local.day)
    return f"{day} {MONTHS_FR[local.month - 1]} {local.year}"


def date_en(value: datetime, tz_name: str) -> str:
    local = value.astimezone(ZoneInfo(tz_name))
    return f"{MONTHS_EN[local.month - 1]} {local.day}, {local.year}"


def _qr_svg(url: str) -> io.BytesIO:
    buffer = io.BytesIO()
    segno.make(url, error="m", micro=False).save(
        buffer, kind="svg", border=0, xmldecl=False, omitsize=True, dark="#000"
    )
    buffer.seek(0)
    return buffer


def render(data: DocumentData) -> bytes:
    pdf = FPDF(unit="mm", format="A4", orientation="L" if data.landscape else "P")
    pdf.set_creation_date(data.issued_at)
    pdf.set_title(data.document_title)
    pdf.set_author(data.edition_title)
    pdf.set_creator("GEST-CONF")
    add_fonts(pdf)
    pdf.set_auto_page_break(auto=False)
    margin = 18.0
    pdf.set_margins(margin, margin, margin)
    pdf.add_page()
    width = pdf.w - 2 * margin

    # En-tête : image de l'institution, sinon bandeau du titre de l'édition.
    if data.header_png:
        pdf.image(
            io.BytesIO(data.header_png), x=margin, y=10, w=width, h=30, keep_aspect_ratio=True
        )
        y = 44.0
    else:
        pdf.set_fill_color(*BAND_COLOR)
        pdf.rect(0, 0, pdf.w, 24, style="F")
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(FONT, "B", 13)
        pdf.set_xy(margin, 8)
        pdf.cell(width, 8, data.edition_title, align="C")
        y = 34.0

    # Titre FR puis EN.
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "B", 24)
    pdf.set_xy(margin, y)
    pdf.multi_cell(width, 11, data.title_fr, align="C", new_x="LMARGIN", new_y="NEXT")
    if data.title_en:
        pdf.set_text_color(*MUTED)
        pdf.set_font(FONT, "", 14)
        pdf.multi_cell(width, 7, data.title_en, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # Texte FR puis EN.
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "", 13)
    pdf.multi_cell(width, 7, data.body_fr, align="C", new_x="LMARGIN", new_y="NEXT")
    if data.body_en:
        pdf.ln(3)
        pdf.set_text_color(*MUTED)
        pdf.set_font(FONT, "", 11)
        pdf.multi_cell(width, 6, data.body_en, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(FONT, "", 10)
    issued = (
        f"Fait le {date_fr(data.issued_at, data.timezone)} · "
        f"Issued on {date_en(data.issued_at, data.timezone)}"
    )
    pdf.multi_cell(width, 5, issued, align="C", new_x="LMARGIN", new_y="NEXT")

    # Bloc de signature et QR de vérification, en bas de page.
    bottom = pdf.h - margin - (12 if (data.footer_fr or data.footer_en) else 0)
    block_width = 85.0
    qr_size = 28.0
    signature_x = pdf.w - margin - block_width if data.signature_right else margin
    qr_x = margin if data.signature_right else pdf.w - margin - qr_size
    block_top = bottom - 50
    if data.signature_png:
        pdf.image(
            io.BytesIO(data.signature_png),
            x=signature_x,
            y=block_top,
            w=block_width,
            h=24,
            keep_aspect_ratio=True,
        )
    pdf.set_xy(signature_x, block_top + 26)
    pdf.set_font(FONT, "B", 11)
    pdf.multi_cell(block_width, 5.5, data.signatory_name, align="C", new_x="LEFT", new_y="NEXT")
    pdf.set_font(FONT, "", 9.5)
    pdf.multi_cell(block_width, 4.5, data.signatory_title_fr, align="C", new_x="LEFT", new_y="NEXT")
    if data.signatory_title_en:
        pdf.set_text_color(*MUTED)
        pdf.multi_cell(
            block_width, 4.5, data.signatory_title_en, align="C", new_x="LEFT", new_y="NEXT"
        )
        pdf.set_text_color(0, 0, 0)
    pdf.image(_qr_svg(data.verification_url), x=qr_x, y=bottom - qr_size - 9, w=qr_size, h=qr_size)
    pdf.set_font(FONT, "", 7)
    pdf.set_text_color(*MUTED)
    caption_width = 70.0
    caption_x = qr_x if data.signature_right else qr_x + qr_size - caption_width
    pdf.set_xy(caption_x, bottom - 8)
    pdf.multi_cell(
        caption_width,
        3.2,
        f"Vérifier · Verify : {data.verification_url}",
        align="L" if data.signature_right else "R",
    )

    # Pied de page.
    footer = " · ".join(part for part in (data.footer_fr, data.footer_en) if part)
    if footer:
        pdf.set_xy(margin, pdf.h - margin - 8)
        pdf.set_font(FONT, "", 8)
        pdf.multi_cell(width, 4, footer, align="C")
    return bytes(pdf.output())
