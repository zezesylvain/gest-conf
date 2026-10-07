"""Exports CSV et XLSX ouverts dans un tableur (exports de masse journalisés, RG-17).

CSV : séparateur « ; » et BOM UTF-8, ouverture directe dans un tableur configuré en
français. Chaque cellule est neutralisée contre l'injection de formules (apostrophe devant
``=``, ``+``, ``-``, ``@``, tabulation, retour chariot), comme l'export des soumissions (L3).

XLSX (plan L8, N13 ; bilan de L8.0) : ``openpyxl`` en mode « écriture seule ». Une chaîne
affectée telle quelle et commençant par ``=`` deviendrait une **formule** : chaque chaîne
est donc typée texte (``inlineStr``), sans apostrophe, qui y apparaîtrait telle quelle ; les
nombres (``int``, ``Decimal``) restent des nombres.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from decimal import Decimal
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


XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def xlsx_bytes(header: Sequence[str], rows: Iterable[Sequence[Any]], *, title: str) -> bytes:
    """Classeur d'une feuille : en-tête puis lignes ; chaînes en texte, jamais en formule."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet(title[:31] or "Export")

    def cells(values: Sequence[Any]) -> list:
        out = []
        for value in values:
            if value is None:
                value = ""
            if isinstance(value, bool):
                value = str(value)
            item = WriteOnlyCell(
                sheet, value=value if isinstance(value, int | Decimal) else str(value)
            )
            if not isinstance(value, int | Decimal):
                item.data_type = "s"
            out.append(item)
        return out

    sheet.append(cells(header))
    for row in rows:
        sheet.append(cells(row))
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def xlsx_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type=XLSX_CONTENT_TYPE)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response
