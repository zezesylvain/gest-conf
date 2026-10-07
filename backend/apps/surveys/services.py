"""Questionnaires de satisfaction (plan L8, N12 ; RG-21 proposée).

- Questionnaire **global** de l'édition, ou d'une **session** ; titres et introduction FR et
  EN ; questions fermées (note de 1 à 5, choix unique, choix multiples) ou texte libre de
  1 000 caractères au plus ; modèle par défaut proposé à la création.
- Ouverture et clôture **saisies en heure locale de l'édition** (D13). À la publication, deux
  tâches datées de ``run_jobs`` : les **invitations** à l'ouverture (cloche et e-mail aux
  personnes présentes : pointage non annulé, à l'accueil ou à l'entrée de la session), puis
  **une** relance par e-mail à mi-parcours, aux seules personnes qui n'ont pas répondu.
- **RG-21** : la réponse est enregistrée sans lien avec la personne ni avec son invitation
  (voir ``models``), l'invitation est marquée « répondu » dans la **même transaction** ;
  rien au journal ne relie une personne à une réponse ; une réponse par personne.
- Questions **verrouillées** dès la première réponse : on duplique le questionnaire.
- Résultats agrégés à partir de **5 réponses** ; textes libres exportés dans un ordre
  aléatoire.
"""

from __future__ import annotations

import datetime as dt
import random
from collections import Counter
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone, translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services.roles import ensure_editable
from apps.communications.models import NotificationKind
from apps.communications.notifications import notify
from apps.communications.services import bulk_hourly_limit, queue_email, resolve_locale
from apps.conferences.models import Edition
from apps.conferences.services import local_to_utc, utc_to_local
from apps.core import jobs
from apps.core.actor import Actor
from apps.core.audit import mask_emails, record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import JobPriority
from apps.surveys.models import (
    QuestionKind,
    Survey,
    SurveyInvitation,
    SurveyQuestion,
    SurveyResponse,
    SurveyScope,
    SurveyStatus,
)

INVITE_JOB = "surveys.invite"
REMIND_JOB = "surveys.remind"
BATCH = 200
THRESHOLD = 5  # résultats agrégés affichés à partir de 5 réponses (N12)
TEXT_LIMIT = 1000
INVITATION_TEMPLATE = "surveys/email/invitation"
REMINDER_TEMPLATE = "surveys/email/reminder"
MY_SURVEYS_PATH = "/compte/questionnaires/"

SURVEY_FIELDS = frozenset(
    {
        "scope",
        "session",
        "title_fr",
        "title_en",
        "intro_fr",
        "intro_en",
        "opens_local",
        "closes_local",
    }
)
# Une fois publié : les titres, l'introduction et la clôture se corrigent ; l'ouverture, la
# portée et la session non (les invitations sont programmées).
EDITABLE_AFTER_PUBLICATION = frozenset(
    {"title_fr", "title_en", "intro_fr", "intro_en", "closes_local"}
)
QUESTION_FIELDS = frozenset({"kind", "label_fr", "label_en", "choices", "required", "position"})

# Modèle par défaut (N12) : organisation, programme, lieu, accueil, recommandation,
# commentaire. Libellés FR et EN écrits ici : ils deviennent des données de l'édition.
DEFAULT_QUESTIONS = (
    ("rating", "Organisation générale de la conférence", "Overall organisation of the conference"),
    ("rating", "Qualité du programme scientifique", "Quality of the scientific programme"),
    ("rating", "Lieu et salles", "Venue and rooms"),
    ("rating", "Accueil et information sur place", "Welcome and on-site information"),
    (
        "rating",
        "Recommanderiez-vous cette conférence à un collègue ?",
        "Would you recommend this conference to a colleague?",
    ),
    ("text", "Commentaires et suggestions", "Comments and suggestions"),
)


# --- Saisie ------------------------------------------------------------------------------


def _text(data: Mapping[str, Any], name: str, limit: int, errors: dict) -> str:
    value = (data.get(name) or "").strip()
    if len(value) > limit:
        errors[name] = [_("%(limit)s caractères au plus.") % {"limit": limit}]
    return value


def _clean_survey(edition: Edition, data: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    from apps.program.models import Session

    unknown = set(data) - SURVEY_FIELDS
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    for name, limit in (
        ("title_fr", 150),
        ("title_en", 150),
        ("intro_fr", 2000),
        ("intro_en", 2000),
    ):
        if name in data:
            clean[name] = _text(data, name, limit, errors)
    if (creating or "title_fr" in clean) and not clean.get("title_fr"):
        errors["title_fr"] = [_("Titre obligatoire.")]
    if "scope" in data or creating:
        scope = data.get("scope", SurveyScope.GLOBAL)
        if scope not in SurveyScope.values:
            errors["scope"] = [_("Portée inconnue.")]
        clean["scope"] = scope
    if "session" in data:
        session_id = data["session"]
        if session_id is None:
            clean["session"] = None
        else:
            session = Session.objects.filter(pk=session_id, edition=edition).first()
            if session is None:
                errors["session"] = [_("Session de l'édition attendue.")]
            clean["session"] = session
    for local, field in (("opens_local", "opens_at"), ("closes_local", "closes_at")):
        if local in data:
            value = data[local]
            if value is None:
                clean[field] = None
            elif not isinstance(value, dt.datetime):
                errors[local] = [_("Date et heure attendues.")]
            else:
                try:
                    clean[field] = local_to_utc(value, edition.timezone)
                except Invalid as error:
                    errors[local] = list(error.fields.get("at_local", [error.message]))
    if errors:
        raise Invalid(fields=errors)
    return clean


def _check_shape(survey: Survey) -> None:
    errors: dict[str, list] = {}
    if survey.scope == SurveyScope.SESSION and survey.session_id is None:
        errors["session"] = [_("Choisissez la session.")]
    if survey.scope == SurveyScope.GLOBAL:
        survey.session = None
    if survey.opens_at and survey.closes_at and survey.closes_at <= survey.opens_at:
        errors["closes_local"] = [_("Clôture après l'ouverture.")]
    if errors:
        raise Invalid(fields=errors)


def _snapshot(survey: Survey) -> dict[str, Any]:
    return mask_emails(
        {
            "title_fr": survey.title_fr,
            "scope": survey.scope,
            "session": survey.session_id,
            "opens_at": survey.opens_at.isoformat() if survey.opens_at else None,
            "closes_at": survey.closes_at.isoformat() if survey.closes_at else None,
        }
    )


def _locked(survey_id: int) -> Survey:
    return Survey.objects.select_for_update().select_related("edition").get(pk=survey_id)


def _check_unlocked(survey: Survey) -> None:
    if survey.locked_at is not None:
        raise RuleViolation(
            _(
                "Des réponses ont été reçues : les questions ne changent plus. Dupliquez le "
                "questionnaire."
            ),
            code=ErrorCode.SURVEY_LOCKED,
        )


@transaction.atomic
def create_survey(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor, default_questions: bool = True
) -> Survey:
    ensure_editable(edition)
    survey = Survey(
        edition=edition, created_by=actor.user, **_clean_survey(edition, data, creating=True)
    )
    _check_shape(survey)
    survey.save()
    if default_questions:
        SurveyQuestion.objects.bulk_create(
            SurveyQuestion(
                survey=survey,
                position=index,
                kind=kind,
                label_fr=label_fr,
                label_en=label_en,
                required=kind == QuestionKind.RATING,
            )
            for index, (kind, label_fr, label_en) in enumerate(DEFAULT_QUESTIONS)
        )
    record("survey.created", actor=actor, edition=edition, obj=survey, after=_snapshot(survey))
    return survey


@transaction.atomic
def update_survey(survey: Survey, data: Mapping[str, Any], *, actor: Actor) -> Survey:
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    if survey.status == SurveyStatus.PUBLISHED:
        frozen = sorted(set(data) - EDITABLE_AFTER_PUBLICATION)
        if frozen:
            raise Invalid(
                fields={name: [_("Questionnaire publié : non modifiable.")] for name in frozen}
            )
    before = _snapshot(survey)
    for name, value in _clean_survey(survey.edition, data, creating=False).items():
        setattr(survey, name, value)
    _check_shape(survey)
    survey.save()
    after = _snapshot(survey)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "survey.updated",
            actor=actor,
            edition=survey.edition,
            obj=survey,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return survey


@transaction.atomic
def delete_survey(survey: Survey, *, actor: Actor) -> None:
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    if survey.status != SurveyStatus.DRAFT:
        raise RuleViolation(_("Seul un brouillon se supprime."), code=ErrorCode.INVALID_TRANSITION)
    record(
        "survey.deleted", actor=actor, edition=survey.edition, obj=survey, before=_snapshot(survey)
    )
    survey.questions.all().delete()
    survey.delete()


@transaction.atomic
def duplicate(survey: Survey, *, actor: Actor) -> Survey:
    """Copie en brouillon, questions comprises, sans dates (N12, comme une grille)."""
    ensure_editable(survey.edition)
    copy = Survey.objects.create(
        edition=survey.edition,
        scope=survey.scope,
        session=survey.session,
        title_fr=survey.title_fr,
        title_en=survey.title_en,
        intro_fr=survey.intro_fr,
        intro_en=survey.intro_en,
        created_by=actor.user,
    )
    SurveyQuestion.objects.bulk_create(
        SurveyQuestion(
            survey=copy,
            position=question.position,
            kind=question.kind,
            label_fr=question.label_fr,
            label_en=question.label_en,
            choices=question.choices,
            required=question.required,
        )
        for question in survey.questions.all()
    )
    record(
        "survey.duplicated",
        actor=actor,
        edition=survey.edition,
        obj=copy,
        after={"source": survey.pk},
    )
    return copy


# --- Questions ---------------------------------------------------------------------------


def _clean_choices(value: Any, errors: dict) -> list[dict[str, str]]:
    if not isinstance(value, list) or not 2 <= len(value) <= 12:
        errors["choices"] = [_("De 2 à 12 choix.")]
        return []
    clean = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            errors["choices"] = [_("Choix mal formé.")]
            return []
        label_fr = str(item.get("label_fr") or "").strip()
        label_en = str(item.get("label_en") or "").strip()
        if not label_fr or len(label_fr) > 150 or len(label_en) > 150:
            errors["choices"] = [_("Chaque choix a un libellé (150 caractères au plus).")]
            return []
        clean.append({"value": str(index + 1), "label_fr": label_fr, "label_en": label_en})
    return clean


def _clean_question(data: Mapping[str, Any], *, kind: str | None) -> dict[str, Any]:
    unknown = set(data) - QUESTION_FIELDS
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    if "kind" in data or kind is None:
        kind = data.get("kind")
        if kind not in QuestionKind.values:
            errors["kind"] = [_("Type de question inconnu.")]
        clean["kind"] = kind
    for name in ("label_fr", "label_en"):
        if name in data:
            clean[name] = _text(data, name, 300, errors)
    if "required" in data:
        clean["required"] = bool(data["required"])
    if "position" in data:
        position = data["position"]
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            errors["position"] = [_("Position positive ou nulle attendue.")]
        clean["position"] = position
    if kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE):
        if "choices" in data or "kind" in data:
            clean["choices"] = _clean_choices(data.get("choices"), errors)
    elif "kind" in data:
        clean["choices"] = []
    if errors:
        raise Invalid(fields=errors)
    return clean


@transaction.atomic
def add_question(survey: Survey, data: Mapping[str, Any], *, actor: Actor) -> SurveyQuestion:
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    _check_unlocked(survey)
    clean = _clean_question(data, kind=None)
    if not clean.get("label_fr"):
        raise Invalid(fields={"label_fr": [_("Libellé obligatoire.")]})
    clean.setdefault("position", survey.questions.count())
    question = SurveyQuestion.objects.create(survey=survey, **clean)
    record(
        "survey.question_added",
        actor=actor,
        edition=survey.edition,
        obj=survey,
        after=mask_emails({"question": question.pk, "label_fr": question.label_fr}),
    )
    return question


@transaction.atomic
def update_question(
    question: SurveyQuestion, data: Mapping[str, Any], *, actor: Actor
) -> SurveyQuestion:
    survey = question.survey
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    _check_unlocked(survey)
    question = SurveyQuestion.objects.select_for_update().get(pk=question.pk)
    for name, value in _clean_question(data, kind=question.kind).items():
        setattr(question, name, value)
    if not question.label_fr:
        raise Invalid(fields={"label_fr": [_("Libellé obligatoire.")]})
    question.save()
    record(
        "survey.question_updated",
        actor=actor,
        edition=survey.edition,
        obj=survey,
        after=mask_emails({"question": question.pk, "fields": sorted(data)}),
    )
    return question


@transaction.atomic
def delete_question(question: SurveyQuestion, *, actor: Actor) -> None:
    survey = question.survey
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    _check_unlocked(survey)
    record(
        "survey.question_deleted",
        actor=actor,
        edition=survey.edition,
        obj=survey,
        before={"question": question.pk},
    )
    question.delete()


# --- Publication, invitations et relance -------------------------------------------------


@transaction.atomic
def publish(survey: Survey, *, actor: Actor, now: dt.datetime | None = None) -> Survey:
    """Programme les invitations (à l'ouverture) et la relance (à mi-parcours)."""
    now = now or timezone.now()
    ensure_editable(survey.edition)
    survey = _locked(survey.pk)
    if survey.status != SurveyStatus.DRAFT:
        raise RuleViolation(_("Questionnaire déjà publié."), code=ErrorCode.INVALID_TRANSITION)
    errors: dict[str, list] = {}
    if not survey.opens_at:
        errors["opens_local"] = [_("Ouverture obligatoire.")]
    if not survey.closes_at:
        errors["closes_local"] = [_("Clôture obligatoire.")]
    elif survey.closes_at <= now:
        errors["closes_local"] = [_("Clôture dans le passé.")]
    if not survey.questions.exists():
        errors["questions"] = [_("Au moins une question.")]
    if errors:
        raise Invalid(fields=errors)
    _check_shape(survey)
    survey.status = SurveyStatus.PUBLISHED
    survey.published_at = now
    survey.save()
    opens = max(survey.opens_at, now)
    jobs.enqueue(
        INVITE_JOB,
        {"survey_id": survey.pk},
        run_at=opens,
        priority=JobPriority.BULK,
        dedup_key=f"survey:{survey.pk}:invite:0",
    )
    jobs.enqueue(
        REMIND_JOB,
        {"survey_id": survey.pk},
        run_at=reminder_at(survey, opens),
        priority=JobPriority.BULK,
        dedup_key=f"survey:{survey.pk}:remind:0",
    )
    record(
        "survey.published", actor=actor, edition=survey.edition, obj=survey, after=_snapshot(survey)
    )
    return survey


def reminder_at(survey: Survey, opens: dt.datetime) -> dt.datetime:
    """Une relance, à mi-chemin de l'ouverture et de la clôture (précision de N12)."""
    return opens + (survey.closes_at - opens) / 2


def is_open(survey: Survey, now: dt.datetime | None = None) -> bool:
    now = now or timezone.now()
    return (
        survey.status == SurveyStatus.PUBLISHED
        and survey.opens_at is not None
        and survey.closes_at is not None
        and survey.opens_at <= now < survey.closes_at
    )


def invitees(survey: Survey) -> QuerySet[User]:
    """Personnes présentes (L7) : pointage non annulé à l'accueil ou ailleurs pour un
    questionnaire global, à l'entrée de la session pour un questionnaire de session."""
    from apps.events.models import Checkin

    checkins = Checkin.objects.filter(edition=survey.edition, active_key__isnull=False)
    if survey.scope == SurveyScope.SESSION:
        checkins = checkins.filter(session=survey.session_id)
    return User.objects.filter(
        pk__in=checkins.values("registration__user_id"),
        is_active=True,
        anonymized_at__isnull=True,
    ).order_by("pk")


def _link(survey: Survey) -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}{MY_SURVEYS_PATH}{survey.pk}"


def _context(survey: Survey, locale: str) -> dict[str, str]:
    edition = survey.edition
    english = locale == "en"
    closes = utc_to_local(survey.closes_at, edition.timezone)
    with translation.override(locale):
        closes_text = closes.strftime("%d/%m/%Y %H:%M" if not english else "%Y-%m-%d %H:%M")
    return {
        "edition_title": edition.title_en if english and edition.title_en else edition.title_fr,
        "survey_title": survey.title_en if english and survey.title_en else survey.title_fr,
        "closes": closes_text,
        "link": _link(survey),
    }


def _stagger(start: dt.datetime, index: int, now: dt.datetime) -> dt.datetime:
    """Étalement des e-mails groupés : un lot égal à la moitié du plafond par heure."""
    return max(start + dt.timedelta(hours=index // bulk_hourly_limit()), now)


def _send(survey: Survey, user: User, template: str, *, run_at: dt.datetime, key: str) -> None:
    locale = resolve_locale(None, user)
    queue_email(
        template_code=template,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=_context(survey, locale),
        idempotency_key=key,
        edition=survey.edition,
        bulk=True,
        run_at=run_at,
    )


def invite_batch(survey_id: int, *, now: dt.datetime | None = None) -> bool:
    """Un lot d'invitations ; ``True`` s'il en reste. Idempotent (une invitation par
    personne, clé d'e-mail ``survey:<id>:invite:<compte>``)."""
    now = now or timezone.now()
    with transaction.atomic():
        survey = (
            Survey.objects.select_for_update()
            .select_related("edition")
            .filter(pk=survey_id)
            .first()
        )
        if survey is None or survey.invitations_done or not is_open(survey, now):
            return False
        batch = list(invitees(survey).filter(pk__gt=survey.invite_cursor)[:BATCH])
        done = set(
            SurveyInvitation.objects.filter(survey=survey, user__in=batch).values_list(
                "user_id", flat=True
            )
        )
        sent = survey.invitations.count()
        today = timezone.localdate(now)
        payload = {
            "edition_id": survey.edition_id,
            "edition_code": survey.edition.code,
            "survey_id": survey.pk,
            "title_fr": survey.title_fr,
            "title_en": survey.title_en,
        }
        for user in batch:
            if user.pk in done:
                continue
            SurveyInvitation.objects.create(survey=survey, user=user, invited_on=today)
            notify(user, NotificationKind.SURVEY_INVITATION, payload)
            _send(
                survey,
                user,
                INVITATION_TEMPLATE,
                run_at=_stagger(now, sent, now),
                key=f"survey:{survey.pk}:invite:{user.pk}",
            )
            sent += 1
        if batch:
            survey.invite_cursor = batch[-1].pk
        more = len(batch) == BATCH
        survey.invitations_done = not more
        survey.save(update_fields=["invite_cursor", "invitations_done", "updated_at"])
        if more:
            jobs.enqueue(
                INVITE_JOB,
                {"survey_id": survey.pk},
                priority=JobPriority.BULK,
                dedup_key=f"survey:{survey.pk}:invite:{survey.invite_cursor}",
            )
    return more


def remind_batch(survey_id: int, *, now: dt.datetime | None = None) -> bool:
    """Un lot de la relance unique : invitations sans réponse ni relance."""
    now = now or timezone.now()
    with transaction.atomic():
        survey = (
            Survey.objects.select_for_update()
            .select_related("edition")
            .filter(pk=survey_id)
            .first()
        )
        if survey is None or survey.reminders_done or not is_open(survey, now):
            return False
        batch = list(
            SurveyInvitation.objects.filter(
                survey=survey,
                answered_on__isnull=True,
                reminded_on__isnull=True,
                pk__gt=survey.remind_cursor,
                user__is_active=True,
                user__anonymized_at__isnull=True,
            )
            .select_related("user")
            .order_by("pk")[:BATCH]
        )
        today = timezone.localdate(now)
        for index, invitation in enumerate(batch):
            _send(
                survey,
                invitation.user,
                REMINDER_TEMPLATE,
                run_at=_stagger(now, index, now),
                key=f"survey:{survey.pk}:remind:{invitation.user_id}",
            )
        SurveyInvitation.objects.filter(pk__in=[item.pk for item in batch]).update(
            reminded_on=today
        )
        if batch:
            survey.remind_cursor = batch[-1].pk
        more = len(batch) == BATCH
        survey.reminders_done = not more
        survey.save(update_fields=["remind_cursor", "reminders_done", "updated_at"])
        if more:
            jobs.enqueue(
                REMIND_JOB,
                {"survey_id": survey.pk},
                priority=JobPriority.BULK,
                dedup_key=f"survey:{survey.pk}:remind:{survey.remind_cursor}",
            )
    return more


# --- Réponse (RG-21) ---------------------------------------------------------------------


def invitation_of(survey: Survey, user: User) -> SurveyInvitation | None:
    return SurveyInvitation.objects.filter(survey=survey, user=user).first()


def my_invitations(user: User) -> list[SurveyInvitation]:
    return list(
        SurveyInvitation.objects.filter(user=user, survey__status=SurveyStatus.PUBLISHED)
        .select_related("survey__edition", "survey__session")
        .order_by("-survey__opens_at", "-id")
    )


def _clean_answers(survey: Survey, answers: Mapping[str, Any]) -> dict[str, Any]:
    questions = {str(question.pk): question for question in survey.questions.all()}
    unknown = set(map(str, answers)) - set(questions)
    if unknown:
        raise Invalid(fields={"answers": [_("Question inconnue.")]})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    for key, question in questions.items():
        value = answers.get(key, answers.get(int(key)))
        empty = value in (None, "", [])
        if empty:
            if question.required:
                errors[key] = [_("Réponse obligatoire.")]
            continue
        choices = {choice["value"] for choice in question.choices}
        if question.kind == QuestionKind.RATING:
            if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 5:
                errors[key] = [_("Note de 1 à 5.")]
            else:
                clean[key] = value
        elif question.kind == QuestionKind.SINGLE:
            if str(value) not in choices:
                errors[key] = [_("Choix inconnu.")]
            else:
                clean[key] = str(value)
        elif question.kind == QuestionKind.MULTIPLE:
            values = sorted({str(item) for item in value}) if isinstance(value, list) else None
            if not values or not set(values) <= choices:
                errors[key] = [_("Choix inconnu.")]
            else:
                clean[key] = values
        else:
            text = str(value).strip()
            if len(text) > TEXT_LIMIT:
                errors[key] = [_("%(limit)s caractères au plus.") % {"limit": TEXT_LIMIT}]
            elif text:
                clean[key] = text
    if errors:
        raise Invalid(fields=errors)
    return clean


@transaction.atomic
def answer(
    survey: Survey, user: User, answers: Mapping[str, Any], *, now: dt.datetime | None = None
) -> None:
    """RG-21 : une réponse par personne invitée, enregistrée sans lien avec elle ; l'invitation
    est marquée « répondu » (au jour près) dans la même transaction. Rien n'est journalisé."""
    now = now or timezone.now()
    # Même ordre de verrouillage que les invitations et la relance : le questionnaire, puis
    # l'invitation (pas d'interblocage).
    survey = _locked(survey.pk)
    invitation = (
        SurveyInvitation.objects.select_for_update().filter(survey=survey, user=user).first()
    )
    if invitation is None:
        raise RuleViolation(
            _("Vous n'êtes pas invité à ce questionnaire."), code=ErrorCode.SURVEY_NOT_OPEN
        )
    if invitation.answered_on is not None:
        raise RuleViolation(_("Vous avez déjà répondu."), code=ErrorCode.SURVEY_ANSWERED)
    if not is_open(survey, now):
        raise RuleViolation(_("Ce questionnaire n'est pas ouvert."), code=ErrorCode.SURVEY_NOT_OPEN)
    clean = _clean_answers(survey, answers)
    SurveyResponse.objects.create(survey=survey, answers=clean)
    invitation.answered_on = timezone.localdate(now)
    invitation.save(update_fields=["answered_on"])
    if survey.locked_at is None:
        survey.locked_at = now
        survey.save(update_fields=["locked_at", "updated_at"])


# --- Résultats ---------------------------------------------------------------------------


def stats(survey: Survey) -> dict[str, int]:
    invited = survey.invitations.count()
    answered = survey.invitations.filter(answered_on__isnull=False).count()
    return {
        "invited": invited,
        "answered": answered,
        "responses": survey.responses.count(),
        "threshold": THRESHOLD,
    }


def _average(values: list[int]) -> Decimal | None:
    if not values:
        return None
    return (Decimal(sum(values)) / Decimal(len(values))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def results(survey: Survey) -> dict[str, Any]:
    """Résultats agrégés (N12) : rien sous le seuil de 5 réponses ; textes libres comptés
    seulement (ils sortent par l'export, mélangés)."""
    data = stats(survey)
    if data["responses"] < THRESHOLD:
        return {**data, "questions": []}
    answers = [response.answers for response in survey.responses.all()]
    questions = []
    for question in survey.questions.all():
        key = str(question.pk)
        given = [item[key] for item in answers if key in item]
        row: dict[str, Any] = {
            "id": question.pk,
            "kind": question.kind,
            "label_fr": question.label_fr,
            "label_en": question.label_en,
            "answers": len(given),
            "average": None,
            "counts": [],
        }
        if question.kind == QuestionKind.RATING:
            counter = Counter(given)
            row["average"] = _average(given)
            row["counts"] = [
                {
                    "value": str(note),
                    "label_fr": str(note),
                    "label_en": str(note),
                    "count": counter[note],
                }
                for note in range(1, 6)
            ]
        elif question.kind in (QuestionKind.SINGLE, QuestionKind.MULTIPLE):
            counter = Counter(
                value for item in given for value in (item if isinstance(item, list) else [item])
            )
            row["counts"] = [
                {**choice, "count": counter[choice["value"]]} for choice in question.choices
            ]
        questions.append(row)
    return {**data, "questions": questions}


def export_rows(
    survey: Survey, *, shuffle: random.Random | None = None
) -> tuple[list[str], list[list[Any]]]:
    """Agrégats par question, puis textes libres dans un **ordre aléatoire** (N12)."""
    data = results(survey)
    if data["responses"] < THRESHOLD:
        raise RuleViolation(
            _("Moins de %(threshold)s réponses : rien n'est exporté.") % {"threshold": THRESHOLD},
            code=ErrorCode.SURVEY_THRESHOLD,
        )
    header = [gettext("Question"), gettext("Réponse"), gettext("Nombre"), gettext("Moyenne")]
    rows: list[list[Any]] = []
    for question in data["questions"]:
        for count in question["counts"]:
            rows.append([question["label_fr"], count["label_fr"], count["count"], ""])
        if question["average"] is not None:
            rows.append([question["label_fr"], "", question["answers"], question["average"]])
    texts = [
        [question.label_fr, response.answers[str(question.pk)], 1, ""]
        for question in survey.questions.filter(kind=QuestionKind.TEXT)
        for response in survey.responses.all()
        if str(question.pk) in response.answers
    ]
    (shuffle or random.SystemRandom()).shuffle(texts)
    return header, rows + texts
