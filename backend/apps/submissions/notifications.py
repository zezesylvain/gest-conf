"""E-mails et notifications de la cloche des soumissions (plan L3, F13 ; étude A2). Mis en
file (e-mails) ou écrites (cloche) dans la transaction de l'opération ; les e-mails partent
après validation par la file de tâches. Une notification ne porte que des éléments de la
soumission (référence, titre, échéance), jamais de donnée d'un tiers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from apps.accounts.services.roles import edition_title
from apps.communications.models import NotificationKind
from apps.communications.notifications import notify
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.core.actor import Actor
from apps.submissions.models import Submission, SubmissionExtension
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.services import call_closed_at

RECEIVED = "submission/email/received"
COAUTHOR = "submission/email/coauthor"
WITHDRAWN = "submission/email/withdrawn"
EXTENSION = "submission/email/extension"
DRAFT_REMINDER = "submission/email/draft_reminder"


def register_submission_templates() -> None:
    register_email_template(RECEIVED, fast_path=True)
    register_email_template(COAUTHOR)
    register_email_template(WITHDRAWN)
    register_email_template(EXTENSION, fast_path=True)
    register_email_template(DRAFT_REMINDER)


def local_datetime(value: datetime | None, tz_name: str, locale: str) -> str:
    """Date et heure dans le fuseau de l'édition, avec le nom du fuseau (D13)."""
    if value is None:
        return "—"
    with translation.override(locale):
        local = timezone.localtime(value, ZoneInfo(tz_name))
        return f"{formats.date_format(local, 'DATETIME_FORMAT')} ({tz_name})"


def submission_link(submission: Submission) -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}/compte/soumissions/{submission.pk}"


def _payload(submission: Submission, **extra: str) -> dict[str, object]:
    """Éléments de la notification : la soumission seulement (règle des tiers)."""
    return {
        "submission_id": submission.pk,
        "reference": submission.reference or "",
        "title": submission.title,
        "edition_code": submission.edition.code,
        **extra,
    }


def _base_context(submission: Submission, locale: str) -> dict[str, str]:
    with translation.override(locale):
        untitled = _("(sans titre)")
    return {
        "title": submission.title or untitled,
        "reference": submission.reference or "",
        "edition_title": edition_title(submission.edition, locale),
    }


def _send_to_submitter(template: str, submission: Submission, **extra: str) -> None:
    user = submission.submitter
    locale = resolve_locale(None, user)
    queue_email(
        template_code=template,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context={**_base_context(submission, locale), **extra},
    )


def on_transition(submission: Submission, from_state: str, to_state: str, actor: Actor) -> None:
    """Effet du workflow : accusé de réception et information des co-auteurs à la première
    soumission ; confirmation du retrait d'une soumission déjà soumise."""
    edition = submission.edition
    if from_state == S.DRAFT and to_state == S.SUBMITTED:
        locale = resolve_locale(None, submission.submitter)
        _send_to_submitter(
            RECEIVED,
            submission,
            call_close=local_datetime(call_closed_at(submission), edition.timezone, locale),
            link=submission_link(submission),
        )
        notify(submission.submitter, NotificationKind.SUBMISSION_RECEIVED, _payload(submission))
        submitter_email = submission.submitter.email.lower()
        submitter_name = " ".join(
            part
            for part in (
                getattr(submission.submitter.profile, "first_name", ""),
                getattr(submission.submitter.profile, "last_name", ""),
            )
            if part
        )
        for author in submission.authors.all():
            if author.email.lower() == submitter_email:
                continue
            locale = resolve_locale(None, author.user)
            queue_email(
                template_code=COAUTHOR,
                to_email=author.email,
                to_user=author.user,
                locale=locale,
                context={**_base_context(submission, locale), "submitter_name": submitter_name},
            )
            # Co-auteur avec compte : cloche aussi, sans lien (pas d'accès avant P2, F5).
            payload = _payload(submission)
            del payload["submission_id"]
            notify(author.user, NotificationKind.COAUTHOR_ADDED, payload)
    elif to_state == S.WITHDRAWN and from_state != S.DRAFT:
        _send_to_submitter(WITHDRAWN, submission)
        notify(submission.submitter, NotificationKind.SUBMISSION_WITHDRAWN, _payload(submission))


def extension_granted(extension: SubmissionExtension) -> None:
    submission = extension.submission
    locale = resolve_locale(None, submission.submitter)
    _send_to_submitter(
        EXTENSION,
        submission,
        until=local_datetime(extension.until, submission.edition.timezone, locale),
        reason=extension.reason,
    )
    notify(
        submission.submitter,
        NotificationKind.EXTENSION_GRANTED,
        _payload(submission, until=extension.until.isoformat()),
    )


def draft_reminder(submission: Submission, closes_at: datetime) -> None:
    """Rappel d'un brouillon avant la clôture (F13, étude A2) : e-mail et cloche."""
    locale = resolve_locale(None, submission.submitter)
    _send_to_submitter(
        DRAFT_REMINDER,
        submission,
        call_close=local_datetime(closes_at, submission.edition.timezone, locale),
        link=submission_link(submission),
    )
    notify(
        submission.submitter,
        NotificationKind.DRAFT_REMINDER,
        _payload(submission, closes_at=closes_at.isoformat()),
    )
