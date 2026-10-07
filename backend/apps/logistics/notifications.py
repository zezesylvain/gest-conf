"""E-mails de l'organisation (plan L8) : récapitulatif quotidien des tâches (N3). Mis en file
dans la transaction de l'opération, envoyés après validation (règle n° 9)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from django.conf import settings
from django.utils import formats, translation
from django.utils.translation import gettext as _

from apps.accounts.models import User
from apps.accounts.services.roles import edition_title
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.conferences.models import Edition
from apps.logistics.models import Task

TASKS_REMINDER = "logistics/email/tasks_reminder"


def register_logistics_templates() -> None:
    register_email_template(TASKS_REMINDER)


def tasks_link(edition: Edition) -> str:
    """Kanban des tâches dans la gestion (L8.8)."""
    return f"{settings.GESTCONF_PUBLIC_URL}/gestion/editions/{edition.pk}/organisation/taches"


def tasks_reminder(
    edition: Edition, user: User, tasks: Sequence[Task], *, today: date, idempotency_key: str
) -> None:
    """Récapitulatif au responsable : ses tâches en retard ou à échéance sous deux jours."""
    locale = resolve_locale(None, user)
    with translation.override(locale):
        lines = []
        for task in tasks:
            when = formats.date_format(task.due_date, "DATE_FORMAT")
            if task.due_date < today:
                lines.append(
                    "- "
                    + _("%(title)s : en retard (échéance %(date)s)")
                    % {"title": task.title, "date": when}
                )
            else:
                lines.append(
                    "- " + _("%(title)s : échéance %(date)s") % {"title": task.title, "date": when}
                )
    queue_email(
        template_code=TASKS_REMINDER,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context={
            "edition_title": edition_title(edition, locale),
            "tasks": "\n".join(lines),
            "count": str(len(lines)),
            "link": tasks_link(edition),
        },
        idempotency_key=idempotency_key,
    )
