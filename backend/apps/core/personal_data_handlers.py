"""Données personnelles portées par ``core`` : journal d'audit (plan L1 §4.9)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.core.models import AuditLog
from apps.core.personal_data import AnonymizationContext

# Export : ses propres actions sur 12 mois (plan §4.9).
AUDIT_EXPORT_WINDOW = timedelta(days=365)


def export_audit(user: Any) -> dict[str, Any]:
    since = timezone.now() - AUDIT_EXPORT_WINDOW
    entries = AuditLog.objects.filter(actor=user, at__gte=since).order_by("at", "id")
    return {
        "audit": [
            {
                "at": entry.at.isoformat(),
                "action": entry.action,
                "edition_id": entry.edition_id,
                "object_type": entry.object_type,
                "object_id": entry.object_id,
            }
            for entry in entries
        ]
    }


def anonymize_audit(user: Any, context: AnonymizationContext) -> None:
    """Le journal est conservé (preuve, D15) ; ses IP et navigateurs sont effacés. Les
    clichés avant/après ne contiennent jamais l'adresse en clair (§7.2)."""
    AuditLog.redact_network_for_user(user, actor=context.actor)
