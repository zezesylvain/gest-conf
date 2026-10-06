"""Contrôles d'intégrité de la facturation (plan L6 §3, RG-14), lancés par
``check_integrity``."""

from __future__ import annotations

import hashlib
from collections import defaultdict

from apps.payments.models import BillingDocument
from apps.payments.services.documents import DOCUMENTS


def check_series() -> list[str]:
    """Numérotation continue de chaque série (édition, nature, année) : 1 à n sans trou."""
    problems = []
    series: dict[tuple[int, str, int], list[int]] = defaultdict(list)
    for edition_id, kind, year, sequence in BillingDocument.objects.values_list(
        "edition_id", "kind", "year", "sequence"
    ).order_by("edition_id", "kind", "year", "sequence"):
        series[(edition_id, kind, year)].append(sequence)
    for (edition_id, kind, year), sequences in series.items():
        if sequences != list(range(1, len(sequences) + 1)):
            problems.append(f"série {kind} {year} de l'édition {edition_id} : numérotation à trous")
    return problems


def check_files() -> list[str]:
    """Chaque pièce a son PDF, d'empreinte inchangée (pièce immuable)."""
    problems = []
    for document in BillingDocument.objects.only("pk", "number", "storage_name", "sha256"):
        try:
            data = DOCUMENTS.read(document.storage_name)
        except FileNotFoundError:
            problems.append(f"pièce {document.number} : fichier absent")
            continue
        if hashlib.sha256(data).hexdigest() != document.sha256:
            problems.append(f"pièce {document.number} : empreinte modifiée")
    return problems
