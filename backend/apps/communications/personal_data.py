"""Données personnelles du registre d'envoi (plan L1 §4.9, D15)."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import reduce
from operator import or_
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.communications.models import (
    AnnouncementDelivery,
    AnnouncementOptOut,
    OutboxEmail,
    OutboxStatus,
)
from apps.core.personal_data import AnonymizationContext

ANONYMIZED_SUBJECT = "[anonymisé]"
# D15 (non validée) : métadonnées d'envoi conservées 12 mois.
METADATA_RETENTION = timedelta(days=365)


def _rows_for(user: Any, emails: frozenset[str]) -> Q:
    condition = Q(to_user=user)
    for email in emails:
        condition |= Q(to_email__iexact=email)
    return condition


def export_emails(user: Any) -> dict[str, Any]:
    """E-mails adressés au compte : gabarit, objet, dates, statut (sans corps)."""
    rows = OutboxEmail.objects.filter(to_user=user).order_by("created_at", "id")
    return {
        "emails": [
            {
                "template": row.template_code,
                "subject": row.subject,
                "status": row.status,
                "created_at": row.created_at.isoformat(),
                "sent_at": row.sent_at.isoformat() if row.sent_at else None,
            }
            for row in rows
        ]
    }


def anonymize_emails(user: Any, context: AnonymizationContext) -> None:
    """Lignes liées au compte (par ``to_user`` ou par l'une de ses adresses) : adresse
    anonymisée, objet remplacé, corps purgé. Les corps d'autres e-mails qui citent encore
    une de ses adresses ou son nom (invitation qu'il a envoyée, par exemple) sont purgés."""
    now = timezone.now()
    OutboxEmail.objects.filter(_rows_for(user, context.original_emails)).update(
        to_email=context.anonymized_email,
        subject=ANONYMIZED_SUBJECT,
        body_text="",
        body_html="",
        purged_at=now,
    )
    needles = [*context.original_emails, *context.names]
    if needles:
        mentions = reduce(
            or_,
            (
                Q(body_text__icontains=needle)
                | Q(body_html__icontains=needle)
                | Q(subject__icontains=needle)
                for needle in needles
            ),
        )
        OutboxEmail.objects.filter(mentions).update(
            subject=ANONYMIZED_SUBJECT, body_text="", body_html="", purged_at=now
        )


def purge_old_metadata(dry_run: bool, now: datetime) -> int:
    """D15 (non validée) : lignes du registre d'envoi traitées depuis plus de 12 mois."""
    old = OutboxEmail.objects.filter(
        created_at__lt=now - METADATA_RETENTION,
        status__in=(OutboxStatus.SENT, OutboxStatus.FAILED, OutboxStatus.CANCELLED),
    )
    if dry_run:
        return old.count()
    deleted, _per_model = old.delete()
    return deleted


def export_announcements(user: Any) -> dict[str, Any]:
    """Annonces reçues (N11) et désabonnements ; les annonces rédigées sont celles de
    l'édition, pas des données de leur auteur au-delà de la mention « créée par »."""
    deliveries = (
        AnnouncementDelivery.objects.filter(user=user)
        .select_related("announcement__edition")
        .order_by("delivered_at", "id")
    )
    opt_outs = AnnouncementOptOut.objects.filter(user=user).select_related("edition")
    return {
        "announcements_received": [
            {
                "edition": row.announcement.edition.code,
                "title": row.announcement.title_fr,
                "emailed": row.emailed,
                "at": row.delivered_at.isoformat(),
            }
            for row in deliveries
        ],
        "announcement_opt_outs": [
            {"edition": row.edition.code, "at": row.created_at.isoformat()}
            for row in opt_outs.order_by("created_at", "id")
        ],
    }


def anonymize_announcements(user: Any, context: AnonymizationContext) -> None:
    """Les livraisons restent rattachées au compte anonymisé (comptes de l'envoi) ; le
    désabonnement n'a plus d'objet."""
    AnnouncementOptOut.objects.filter(user=user).delete()
