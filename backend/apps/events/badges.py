"""Badges imprimables (plan L7, K3 ; bilan de L7.0 : ``fpdf2`` et ``segno``).

**A6** (un badge, 105 sur 148 mm) ou **planche A4** de quatre A6, recto seul, traits de coupe.
Contenu : titre de l'édition, nom (taille adaptée), institution et pays, QR du jeton
d'inscription (vectoriel), référence (secours de la saisie manuelle, K6), bandeau de la
catégorie dans sa couleur. Ni adresse, ni téléphone.

Les badges sont produits à la demande et **jamais stockés** : le jeton qu'ils portent est un
titre d'accès (servis en ``no-store``). Lot du CO : 200 badges au plus par fichier (bilan de
L7.0 : environ 8 s pour 1 000).
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass

import segno
from fpdf import FPDF

from apps.core.pdf import FONT, add_fonts

BATCH_SIZE = 200
WIDTH, HEIGHT = 105.0, 148.0  # A6, mm
MARGIN = 6.0
HEADER_HEIGHT = 20.0
BAND_HEIGHT = 18.0
QR_SIZE = 46.0
HEADER_COLOR = (31, 42, 68)
# Couleurs par défaut des catégories, dans leur ordre (contraste suffisant avec le blanc).
PALETTE = (
    "#1565C0",
    "#2E7D32",
    "#C62828",
    "#6A1B9A",
    "#EF6C00",
    "#00838F",
    "#AD1457",
    "#4E342E",
)


@dataclass(frozen=True, slots=True)
class BadgeData:
    edition_title: str
    name: str
    institution: str
    country: str
    category_label: str
    category_label_en: str
    color: str
    token: str
    reference: str


def default_color(position: int) -> str:
    return PALETTE[position % len(PALETTE)]


def _rgb(color: str) -> tuple[int, int, int]:
    value = color.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _text_on(color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Texte noir sur fond clair, blanc sur fond sombre (luminance relative WCAG)."""

    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in color)
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (0, 0, 0) if luminance > 0.179 else (255, 255, 255)


def _qr_svg(token: str) -> io.BytesIO:
    buffer = io.BytesIO()
    # Sans dimensions, avec viewBox (``omitsize``) : fpdf2 l'étire à la taille demandée.
    segno.make(token, error="m", micro=False).save(
        buffer, kind="svg", border=0, xmldecl=False, omitsize=True, dark="#000"
    )
    buffer.seek(0)
    return buffer


def _fit_size(
    pdf: FPDF, text: str, width: float, start: float, minimum: float, lines: int = 2
) -> float:
    """Plus grande taille (pas de 0,5 pt) où ``text`` tient sur ``lines`` lignes de ``width``
    sans couper de mot (essai à blanc de ``multi_cell``)."""
    size = start
    while size > minimum:
        pdf.set_font(FONT, "B", size)
        longest = max((pdf.get_string_width(word) for word in text.split()), default=0)
        if longest <= width:
            wrapped = pdf.multi_cell(width, size * 0.45, text, dry_run=True, output="LINES")
            if len(wrapped) <= lines:
                return size
        size -= 0.5
    return minimum


def _centered(
    pdf: FPDF, x: float, y: float, width: float, text: str, size: float, style=""
) -> float:
    """Texte centré sur au plus deux lignes ; renvoie l'ordonnée sous le texte."""
    pdf.set_font(FONT, style, size)
    height = size * 0.45
    pdf.set_xy(x, y)
    pdf.multi_cell(width, height, text, align="C", max_line_height=height, new_x="LEFT")
    return pdf.get_y()


def _draw(pdf: FPDF, badge: BadgeData, x: float, y: float) -> None:
    inner = WIDTH - 2 * MARGIN
    # Bandeau de l'édition.
    pdf.set_fill_color(*HEADER_COLOR)
    pdf.rect(x, y, WIDTH, HEADER_HEIGHT, style="F")
    pdf.set_text_color(255, 255, 255)
    title_size = _fit_size(pdf, badge.edition_title, inner, 12, 7)
    _centered(pdf, x + MARGIN, y + 4, inner, badge.edition_title, title_size, "B")
    # Nom, institution, pays.
    pdf.set_text_color(0, 0, 0)
    name_size = _fit_size(pdf, badge.name, inner, 24, 11)
    bottom = _centered(pdf, x + MARGIN, y + HEADER_HEIGHT + 7, inner, badge.name, name_size, "B")
    affiliation = " · ".join(part for part in (badge.institution, badge.country) if part)
    if affiliation:
        pdf.set_text_color(60, 60, 60)
        _centered(pdf, x + MARGIN, bottom + 2, inner, affiliation, 10)
    # QR et référence.
    qr_y = y + HEIGHT - BAND_HEIGHT - QR_SIZE - 9
    pdf.image(_qr_svg(badge.token), x=x + (WIDTH - QR_SIZE) / 2, y=qr_y, w=QR_SIZE, h=QR_SIZE)
    pdf.set_text_color(90, 90, 90)
    pdf.set_font(FONT, "", 7.5)
    pdf.set_xy(x + MARGIN, qr_y + QR_SIZE + 1.5)
    pdf.cell(inner, 3.5, badge.reference, align="C")
    # Bandeau de la catégorie.
    color = _rgb(badge.color)
    pdf.set_fill_color(*color)
    band_y = y + HEIGHT - BAND_HEIGHT
    pdf.rect(x, band_y, WIDTH, BAND_HEIGHT, style="F")
    pdf.set_text_color(*_text_on(color))
    label = badge.category_label.upper()
    pdf.set_font(FONT, "B", _fit_size(pdf, label, inner, 16, 8))
    pdf.set_xy(x + MARGIN, band_y + 3)
    pdf.cell(inner, 7, label, align="C")
    if badge.category_label_en and badge.category_label_en != badge.category_label:
        pdf.set_font(FONT, "", 8)
        pdf.set_xy(x + MARGIN, band_y + 10.5)
        pdf.cell(inner, 4, badge.category_label_en, align="C")
    pdf.set_text_color(0, 0, 0)


def _document(title: str, page_format) -> FPDF:
    pdf = FPDF(unit="mm", format=page_format)
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(0, 0, 0)
    pdf.set_title(title)
    pdf.set_creator("GEST-CONF")
    add_fonts(pdf)
    return pdf


def render_single(badge: BadgeData) -> bytes:
    """Un badge au format A6."""
    pdf = _document(badge.name, (WIDTH, HEIGHT))
    pdf.add_page()
    _draw(pdf, badge, 0, 0)
    return bytes(pdf.output())


def _cut_marks(pdf: FPDF) -> None:
    pdf.set_draw_color(170, 170, 170)
    pdf.set_line_width(0.2)
    with pdf.local_context(dash_pattern={"dash": 2, "gap": 2}):
        pdf.line(WIDTH, 0, WIDTH, 2 * HEIGHT)
        pdf.line(0, HEIGHT, 2 * WIDTH, HEIGHT)


def render_sheets(badges: Sequence[BadgeData], title: str) -> bytes:
    """Planches A4 de quatre badges (deux colonnes, deux rangées)."""
    pdf = _document(title, "A4")
    for index, badge in enumerate(badges):
        if index % 4 == 0:
            pdf.add_page()
            _cut_marks(pdf)
        column, row = index % 2, (index // 2) % 2
        _draw(pdf, badge, column * WIDTH, row * HEIGHT)
    if not badges:
        pdf.add_page()
    return bytes(pdf.output())
