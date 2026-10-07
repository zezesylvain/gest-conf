"""PDF de synthèse des rapports (plan L8, N13 ; ``fpdf2``, règle n° 10).

Un titre, la date de production, puis chaque tableau ; police DejaVu Sans embarquée (noms
hors latin-1). Sert aussi la commande au traiteur (N8), restée sans nom.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from fpdf import FPDF
from fpdf.fonts import FontFace

from apps.core.pdf import FONT, add_fonts


def _cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:,}".replace(",", " ")
    return str(value)


def tables_pdf(
    title: str, subtitle: str, tables: Sequence[Any], *, produced_at: dt.datetime
) -> bytes:
    """``tables`` : objets à attributs ``title``, ``columns`` et ``rows``."""
    pdf = FPDF(format="A4")
    pdf.set_creation_date(produced_at)
    pdf.set_title(title)
    pdf.set_creator("GEST-CONF")
    add_fonts(pdf)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font(FONT, "B", 15)
    pdf.multi_cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 9)
    pdf.multi_cell(0, 5, subtitle, new_x="LMARGIN", new_y="NEXT")
    for table in tables:
        pdf.ln(4)
        pdf.set_font(FONT, "B", 11)
        pdf.multi_cell(0, 6, table.title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(FONT, "", 8.5)
        if not table.rows:
            pdf.multi_cell(0, 5, "—", new_x="LMARGIN", new_y="NEXT")
            continue
        count = len(table.columns)
        first = 190 - 25 * (count - 1) if count > 1 else 190
        widths = (
            max(first, 50),
            *([min(25, (190 - max(first, 50)) / max(count - 1, 1))] * (count - 1)),
        )
        with pdf.table(
            col_widths=widths,
            text_align=("LEFT", *(["RIGHT"] * (count - 1))),
            headings_style=FontFace(emphasis="BOLD"),
            line_height=5,
        ) as grid:
            heading = grid.row()
            for column in table.columns:
                heading.cell(str(column))
            for values in table.rows:
                row = grid.row()
                for value in values:
                    row.cell(_cell(value))
    return bytes(pdf.output())
