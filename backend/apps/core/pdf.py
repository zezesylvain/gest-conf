"""Outils communs des PDF ``fpdf2`` (factures en L6 ; badges, attestations et lettres en L7).

Police DejaVu Sans embarquée en sous-ensemble (noms hors latin-1, ``fonts/README.md``).
"""

from __future__ import annotations

from pathlib import Path

FONTS = Path(__file__).resolve().parent / "fonts"
FONT = "DejaVu"


def add_fonts(pdf) -> None:
    """Déclare DejaVu Sans (normal et gras) dans le document ``fpdf2``."""
    pdf.add_font(FONT, "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font(FONT, "B", str(FONTS / "DejaVuSans-Bold.ttf"))
