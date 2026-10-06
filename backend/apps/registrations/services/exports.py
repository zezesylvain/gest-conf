"""Export CSV des inscriptions (plan L6, J12) : mêmes filtres que la liste, journalisé
(RG-17), réauthentification récente (vue)."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from django.utils.translation import gettext as _

from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.spreadsheet import csv_text


def export_registrations(edition: Edition, rows, *, actor: Actor, filters: dict) -> str:
    zone = ZoneInfo(edition.timezone)

    def local(value) -> str:
        return value.astimezone(zone).strftime("%Y-%m-%d %H:%M") if value else ""

    rows = list(rows)
    content = csv_text(
        [
            _("Référence"),
            _("Nom"),
            _("Adresse électronique"),
            _("Pays"),
            _("Catégorie"),
            _("Statut"),
            _("Période"),
            _("Zone"),
            _("Moyen"),
            _("Total"),
            _("Devise"),
            _("Options"),
            _("Code promo"),
            _("Organisme de facturation"),
            _("Commandée le"),
            _("Confirmée le"),
        ],
        (
            [
                row.reference,
                row.billing_name,
                row.user.email,
                getattr(getattr(row.user, "profile", None), "country", ""),
                row.category.code,
                row.status,
                row.period,
                row.zone,
                row.method,
                row.total,
                row.currency,
                ", ".join(line["code"] for line in row.lines if line["kind"] == "option"),
                row.promo_code.code if row.promo_code_id else "",
                row.billing_organization,
                local(row.created_at),
                local(row.confirmed_at),
            ]
            for row in rows
        ),
    )
    record(
        "registrations.exported",
        actor=actor,
        edition=edition,
        after={"count": len(rows), "filters": filters},
    )
    return content
