"""Exports CSV ouverts dans un tableur (exports de masse journalisés, RG-17).

Séparateur « ; » et BOM UTF-8 : ouverture directe dans un tableur configuré en français.
Chaque cellule est neutralisée contre l'injection de formules (apostrophe devant ``=``,
``+``, ``-``, ``@``, tabulation, retour chariot), comme l'export des soumissions (L3).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

from django.http import HttpResponse

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def cell(value: Any) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def csv_text(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow([cell(item) for item in header])
    for row in rows:
        writer.writerow([cell(item) for item in row])
    return output.getvalue()


def csv_response(content: str, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
