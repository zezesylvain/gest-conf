"""Contrôles d'intégrité de l'organisation (``check_integrity``, plan L8, N17)."""

from __future__ import annotations

import hashlib


def check_task_attachments() -> list[str]:
    """Pièces jointes des tâches présentes et intactes (empreinte)."""
    from apps.logistics.models import TaskAttachment
    from apps.logistics.services.tasks import ATTACHMENTS

    problems = []
    rows = TaskAttachment.objects.only("pk", "storage_name", "sha256")
    for row in rows.iterator(chunk_size=200):
        try:
            data = ATTACHMENTS.read(row.storage_name)
        except FileNotFoundError:
            problems.append(f"pièce jointe {row.pk} : fichier absent")
            continue
        if hashlib.sha256(data).hexdigest() != row.sha256:
            problems.append(f"pièce jointe {row.pk} : fichier modifié (empreinte différente)")
    return problems


def check_budget_proofs() -> list[str]:
    """Justificatifs du budget présents."""
    from apps.logistics.models import BudgetLine
    from apps.logistics.services.budget import PROOFS

    problems = []
    rows = BudgetLine.objects.exclude(proof_storage_name="").only("pk", "proof_storage_name")
    for row in rows.iterator(chunk_size=200):
        if not PROOFS.path(row.proof_storage_name).is_file():
            problems.append(f"ligne de budget {row.pk} : justificatif absent")
    return problems
