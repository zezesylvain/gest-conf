"""E-mails aux relecteurs (plan L4, H6, H15). Mis en file dans la transaction de l'opération,
envoyés après validation. RG-04 : ils ne portent que la référence, le titre, l'échéance et le
lien vers l'espace d'évaluation, jamais l'identité des auteurs."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

from apps.accounts.services.roles import edition_title
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.reviews.models import ReviewAssignment
from apps.submissions.notifications import local_datetime

ASSIGNED = "review/email/assigned"
CANCELLED = "review/email/cancelled"
REMINDER = "review/email/reminder"


def register_review_templates() -> None:
    register_email_template(ASSIGNED)
    register_email_template(CANCELLED)
    register_email_template(REMINDER)


def review_link(assignment: ReviewAssignment) -> str:
    """Formulaire d'évaluation dans la gestion (H1)."""
    base = f"{settings.GESTCONF_PUBLIC_URL}/gestion/editions/{assignment.submission.edition_id}"
    return f"{base}/evaluations/{assignment.pk}"


def _send(template: str, assignment: ReviewAssignment, **extra: str) -> None:
    reviewer = assignment.reviewer
    submission = assignment.submission
    edition = submission.edition
    locale = resolve_locale(None, reviewer)
    with translation.override(locale):
        untitled = _("(sans titre)")
    queue_email(
        template_code=template,
        to_email=reviewer.email,
        to_user=reviewer,
        locale=locale,
        context={
            "title": submission.title or untitled,
            "reference": submission.reference or "",
            "edition_title": edition_title(edition, locale),
            "due": local_datetime(assignment.due_at, edition.timezone, locale),
            "link": review_link(assignment),
            **extra,
        },
    )


def assignment_opened(assignment: ReviewAssignment) -> None:
    """Nouvelle évaluation à faire (évaluation ouverte, étude §5.2 « Notification aux
    relecteurs »)."""
    _send(ASSIGNED, assignment)


def assignment_cancelled(assignment: ReviewAssignment) -> None:
    """Affectation annulée par le président ; le motif, interne au comité, n'est pas repris."""
    _send(CANCELLED, assignment)


def reminder(assignment: ReviewAssignment, kind: str) -> None:
    """Relance (H15) : ``j7``, ``j1`` ou ``late``."""
    _send(REMINDER, assignment, kind=kind)
