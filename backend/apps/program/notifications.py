"""E-mails du programme (plan L5). Mis en file dans la transaction de l'opération, envoyés
après validation (règle n° 9)."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.roles import edition_title
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.conferences.models import Edition
from apps.submissions.models import Submission

WITHDRAWN = "program/email/withdrawn"


def register_program_templates() -> None:
    register_email_template(WITHDRAWN)


def planner_link(edition: Edition) -> str:
    """Planificateur du programme dans la gestion (L5.5)."""
    return f"{settings.GESTCONF_PUBLIC_URL}/gestion/editions/{edition.pk}/programme"


def program_team(edition: Edition) -> list[User]:
    """Destinataires des alertes du programme : CO « programme » et présidents de la
    conférence, sinon administrateurs de l'édition (I1)."""
    active = UserRole.objects.filter(edition=edition, status=UserRoleStatus.ACTIVE).select_related(
        "user"
    )
    team = [
        row.user
        for row in active
        if (row.role == Role.OC_MEMBER and row.oc_function == "program") or row.role == Role.CHAIR
    ]
    if not team:
        team = [row.user for row in active if row.role == Role.ADMIN]
    unique = {user.pk: user for user in team if user.is_active and user.anonymized_at is None}
    return list(unique.values())


def withdrawn_from_programme(submission: Submission, *, was_placed: bool) -> None:
    """I5 : une communication confirmée ou programmée est retirée par son auteur ; le motif
    reste dans la gestion (pas dans l'e-mail)."""
    edition = submission.edition
    for member in program_team(edition):
        locale = resolve_locale(None, member)
        with translation.override(locale):
            untitled = _("(sans titre)")
        queue_email(
            template_code=WITHDRAWN,
            to_email=member.email,
            to_user=member,
            locale=locale,
            context={
                "reference": submission.reference or "",
                "title": submission.title or untitled,
                "edition_title": edition_title(edition, locale),
                "placed": "1" if was_placed else "",
                "link": planner_link(edition),
            },
            idempotency_key=f"program-withdrawn:{submission.pk}:{member.pk}",
        )
