"""Notifications dans l'application (cloche, plan L3 F13) : création, lecture, conservation.

Pas de temps réel (règle n° 9 : ni WebSocket ni file externe) : l'espace compte relit le
nombre de notifications non lues à l'ouverture et à chaque navigation.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.communications.models import Notification, NotificationKind
from apps.core.personal_data import AnonymizationContext

# Notifications renvoyées par /me/notifications (les plus récentes).
RECENT_LIMIT = 50
# D15 (non validée) : notifications lues conservées 6 mois, non lues 12 mois.
READ_RETENTION = timedelta(days=183)
UNREAD_RETENTION = timedelta(days=365)


def notify(
    user: Any, kind: NotificationKind | str, payload: Mapping[str, Any]
) -> Notification | None:
    """Crée une notification pour un compte actif ; rien sans compte (adresse seule)."""
    if user is None or not getattr(user, "is_active", False):
        return None
    return Notification.objects.create(user=user, kind=kind, payload=dict(payload))


def recent(user: Any, limit: int = RECENT_LIMIT) -> list[Notification]:
    return list(Notification.objects.filter(user=user).order_by("-created_at", "-id")[:limit])


def unread_count(user: Any) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


@transaction.atomic
def mark_read(user: Any, ids: Sequence[int] | None = None, now: datetime | None = None) -> int:
    """Marque comme lues les notifications désignées (toutes si ``ids`` est ``None``) ;
    celles d'un autre compte sont ignorées. Renvoie le nombre de lignes modifiées."""
    rows = Notification.objects.filter(user=user, read_at__isnull=True)
    if ids is not None:
        rows = rows.filter(pk__in=list(ids))
    return rows.update(read_at=now or timezone.now())


def export_notifications(user: Any) -> dict[str, Any]:
    return {
        "notifications": [
            {
                "kind": row.kind,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
                "read_at": row.read_at.isoformat() if row.read_at else None,
            }
            for row in Notification.objects.filter(user=user).order_by("created_at", "id")
        ]
    }


def anonymize_notifications(user: Any, context: AnonymizationContext) -> None:
    """Les notifications d'un compte anonymisé n'ont plus de destinataire : supprimées."""
    Notification.objects.filter(user=user).delete()


def purge_old_notifications(dry_run: bool, now: datetime) -> int:
    """D15 (non validée) : notifications lues depuis plus de 6 mois, ou créées depuis plus
    de 12 mois."""
    old = Notification.objects.filter(
        read_at__lt=now - READ_RETENTION
    ) | Notification.objects.filter(created_at__lt=now - UNREAD_RETENTION)
    if dry_run:
        return old.count()
    deleted, _per_model = old.delete()
    return deleted
