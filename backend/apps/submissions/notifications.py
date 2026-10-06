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
SCREENING_REJECTED = "submission/email/screening_rejected"
DECISION = "submission/email/decision"
FINAL_RECEIVED = "submission/email/final_received"


def register_submission_templates() -> None:
    register_email_template(RECEIVED, fast_path=True)
    register_email_template(COAUTHOR)
    register_email_template(WITHDRAWN)
    register_email_template(EXTENSION, fast_path=True)
    register_email_template(DRAFT_REMINDER)
    register_email_template(SCREENING_REJECTED)
    register_email_template(DECISION)
    register_email_template(FINAL_RECEIVED, fast_path=True)


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
    soumission ; confirmation du retrait d'une soumission déjà soumise ; rejet de
    recevabilité motivé (étude §5.2, plan L4 H10), notifié au soumissionnaire."""
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
    elif from_state == S.SCREENING and to_state == S.REJECTED:
        # Motif : celui de la transition, que ``transition()`` vient d'historiser.
        last = submission.status_history.order_by("-at", "-id").first()
        _send_to_submitter(
            SCREENING_REJECTED,
            submission,
            reason=last.reason if last is not None else "",
            link=submission_link(submission),
        )
        notify(submission.submitter, NotificationKind.SCREENING_REJECTED, _payload(submission))


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


def decision_published(decision, comments: list[dict], camera_ready) -> None:
    """RG-09, RG-10 : décision publiée, aux auteurs (soumissionnaire et co-auteurs, une fois
    par adresse) ; commentaires des relecteurs sous pseudonyme, jamais leur identité, leurs
    notes ni les commentaires au comité. Le lien ne va qu'au soumissionnaire (F5)."""
    submission = decision.submission
    edition = submission.edition
    submitter = submission.submitter
    recipients: list[tuple[str, object]] = [(submitter.email, submitter)]
    seen = {submitter.email.casefold()}
    for author in submission.authors.all():
        if author.email and author.email.casefold() not in seen:
            seen.add(author.email.casefold())
            recipients.append((author.email, author.user))
    for email, user in recipients:
        locale = resolve_locale(None, user)
        with translation.override(locale):
            reviews_text = "\n\n".join(
                _("Relecteur %(rank)s :") % {"rank": item["pseudonym_rank"]}
                + "\n"
                + item["comment"]
                for item in comments
            )
        kind = decision.assigned_type
        assigned = ""
        if kind is not None:
            assigned = kind.label_en if locale == "en" and kind.label_en else kind.label_fr
        is_submitter = user is not None and user.pk == submitter.pk
        queue_email(
            template_code=DECISION,
            to_email=email,
            to_user=user,
            locale=locale,
            context={
                **_base_context(submission, locale),
                "outcome": decision.outcome,
                "assigned_type": assigned,
                "chair_comment": decision.comment_to_authors,
                "reviews": reviews_text,
                "camera_ready": local_datetime(camera_ready, edition.timezone, locale)
                if camera_ready
                else "",
                "link": submission_link(submission) if is_submitter else "",
            },
        )
        payload = _payload(submission, outcome=decision.outcome)
        if not is_submitter:
            del payload["submission_id"]
        notify(user, NotificationKind.DECISION_PUBLISHED, payload)


def final_version_received(submission: Submission, stored) -> None:
    """H18 : accusé de réception de la version finale (e-mail et cloche)."""
    _send_to_submitter(FINAL_RECEIVED, submission, link=submission_link(submission))
    notify(submission.submitter, NotificationKind.FINAL_VERSION_RECEIVED, _payload(submission))
