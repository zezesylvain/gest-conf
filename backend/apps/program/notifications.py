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
PASSAGE = "program/email/passage"
PRESENTATION_REMINDER = "program/email/presentation_reminder"


def register_program_templates() -> None:
    register_email_template(WITHDRAWN)
    register_email_template(PASSAGE)
    register_email_template(PRESENTATION_REMINDER)


def agenda_link() -> str:
    """« Mon passage » dans l'espace compte du portail (I8)."""
    return f"{settings.GESTCONF_PUBLIC_URL}/compte/mon-passage"


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


def presentation_reminder(submission: Submission, idempotency_key: str) -> None:
    """Rappel au soumissionnaire : désigner les présentateurs et confirmer sa venue (I5)."""
    from apps.submissions.notifications import submission_link

    submitter = submission.submitter
    edition = submission.edition
    locale = resolve_locale(None, submitter)
    with translation.override(locale):
        untitled = _("(sans titre)")
    queue_email(
        template_code=PRESENTATION_REMINDER,
        to_email=submitter.email,
        to_user=submitter,
        locale=locale,
        context={
            "reference": submission.reference or "",
            "title": submission.title or untitled,
            "edition_title": edition_title(edition, locale),
            "link": submission_link(submission),
        },
        idempotency_key=idempotency_key,
    )


def _recipient(key: str) -> tuple[str, User | None]:
    """Destinataire d'une clé de personne : le compte, sinon l'adresse de l'auteur."""
    kind, _sep, value = key.partition(":")
    if kind == "user":
        user = User.objects.filter(
            pk=int(value), is_active=True, anonymized_at__isnull=True
        ).first()
        return (user.email, user) if user is not None else ("", None)
    return value, User.objects.filter(email__iexact=value, anonymized_at__isnull=True).first()


def passage_changed(edition: Edition, publication, key: str, status: str, items) -> None:
    """I16 : passage nouveau, modifié ou supprimé, une fois par version publiée. L'e-mail
    ne porte que les passages de la personne (date, heure de l'édition, salle, rôle)."""
    from apps.program.services.publication import person_hash

    to_email, user = _recipient(key)
    if not to_email:
        return
    locale = resolve_locale(None, user) if user is not None else "fr"
    with translation.override(locale):
        roles = {
            "presenter": _("présentation"),
            "speaker": _("intervention"),
            "chair": _("présidence de séance"),
            "discussant": _("discussion"),
            "moderator": _("modération"),
            "panelist": _("table ronde"),
        }
        lines = "\n".join(
            # Gabarit traduit : « : » précédé d'une espace en français, pas en anglais.
            _("- {start} · {room} · {role} : {title}").format(
                start=local_datetime_from_iso(item.starts_at, edition.timezone, locale),
                room=item.room or "—",
                role=roles.get(item.role, item.role),
                title=item.title,
            )
            for item in items
        )
    queue_email(
        template_code=PASSAGE,
        to_email=to_email,
        to_user=user,
        locale=locale,
        context={
            "edition_title": edition_title(edition, locale),
            "status": status,
            "passages": lines,
            "link": agenda_link(),
            "has_account": "1" if user is not None else "",
        },
        idempotency_key=f"program-passage:{edition.pk}:{publication.version}:{person_hash(key)}",
    )


def local_datetime_from_iso(value: str, tz_name: str, locale: str) -> str:
    """Date et heure de l'édition, au format des e-mails (fuseau indiqué)."""
    import datetime as dt

    from apps.submissions.notifications import local_datetime

    return local_datetime(dt.datetime.fromisoformat(value), tz_name, locale)
