"""Paramétrage de la conférence et de ses éditions (plan L1 §6, M3).

Toute écriture est journalisée avec l'état avant et après (RG-17, liste blanche
``AUDIT_FIELDS``) et refusée sur une édition archivée (409 ``edition_archived``),
sauf par commande. Le statut ne change que par ``set_edition_status`` (§6.3).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import (
    KEY_DATE_CHAINS,
    Conference,
    Edition,
    EditionStatus,
    KeyDate,
    KeyDateCode,
    SubmissionType,
    Track,
)
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation

EDITION_INFO_FIELDS = (
    "code",
    "slug",
    "year",
    "title_fr",
    "title_en",
    "theme_fr",
    "theme_en",
    "start_date",
    "end_date",
    "venue",
    "city",
    "country",
    "timezone",
    "submission_languages",
)
CONFIDENTIALITY_FIELDS = ("double_blind", "reviewers_per_submission")
TRACK_FIELDS = (
    "code",
    "name_fr",
    "name_en",
    "description_fr",
    "description_en",
    "position",
    "is_active",
)
SUBMISSION_TYPE_FIELDS = (
    "code",
    "label_fr",
    "label_en",
    "description_fr",
    "description_en",
    "default_duration_min",
    "abstract_max_words",
    "file_policy",
    "max_file_mb",
    "position",
    "is_active",
)
KEY_DATE_FIELDS = ("code", "at_local", "label_fr", "label_en", "is_public", "position")


def _validation(exc: ValidationError) -> Invalid:
    if hasattr(exc, "error_dict"):
        return Invalid(fields=exc.message_dict)
    return Invalid(fields={"non_field_errors": exc.messages})


def _save(instance: models.Model, *, exclude: list[str] | None = None) -> None:
    try:
        instance.full_clean(exclude=exclude)
    except ValidationError as exc:
        raise _validation(exc) from exc
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise Invalid(fields={"code": [_("Ce code est déjà utilisé.")]}) from exc


def _writable(edition: Edition, actor: Actor) -> None:
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)


def _apply(instance: models.Model, data: Mapping[str, Any], allowed: tuple[str, ...]) -> list[str]:
    unknown = set(data) - set(allowed)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    changed = [name for name, value in data.items() if getattr(instance, name) != value]
    for name in changed:
        setattr(instance, name, data[name])
    return changed


# --- Conférence et éditions (commandes, D1) ---------------------------------------------


@transaction.atomic
def create_conference(*, slug: str, name_fr: str, name_en: str = "", actor: Actor) -> Conference:
    conference = Conference(slug=slug, name_fr=name_fr, name_en=name_en)
    _save(conference)
    record("conference.created", actor=actor, obj=conference, after=snapshot(conference))
    return conference


@transaction.atomic
def create_edition(*, conference: Conference, actor: Actor, **fields: Any) -> Edition:
    edition = Edition(conference=conference, **fields)
    _save(edition)
    record("edition.created", actor=actor, edition=edition, obj=edition, after=snapshot(edition))
    return edition


@transaction.atomic
def set_current_edition(conference: Conference, edition: Edition, *, actor: Actor) -> Conference:
    if edition.conference_id != conference.pk:
        raise Invalid(fields={"edition": [_("Édition d'une autre conférence.")]})
    before = snapshot(conference)
    conference.current_edition = edition
    conference.save(update_fields=["current_edition", "updated_at"])
    record(
        "conference.current_edition_set",
        actor=actor,
        edition=edition,
        obj=conference,
        before=before,
        after=snapshot(conference),
    )
    return conference


# RG-19 (plan L3 F9) : réglages gelés dès qu'une soumission a été soumise.
FROZEN_FIELDS = ("code", "double_blind")


def has_submitted_work(edition: Edition) -> bool:
    """Une soumission non brouillon existe (condition du gel RG-19)."""
    from django.apps import apps

    Submission = apps.get_model("submissions", "Submission")
    return Submission.objects.filter(edition=edition).exclude(status="draft").exists()


def frozen_fields(edition: Edition) -> list[str]:
    return list(FROZEN_FIELDS) if has_submitted_work(edition) else []


def _is_edition_admin(edition: Edition, actor: Actor) -> bool:
    from apps.accounts.models import UserRole, UserRoleStatus
    from apps.accounts.roles import Role

    if actor.kind != ActorKind.USER:
        return actor.kind == ActorKind.COMMAND
    return UserRole.objects.filter(
        user=actor.user, edition=edition, role=Role.ADMIN, status=UserRoleStatus.ACTIVE
    ).exists()


def _check_frozen(edition: Edition, data: Mapping[str, Any], actor: Actor, reason: str) -> None:
    """RG-19 : ``code`` et ``double_blind`` ne changent plus après la première soumission,
    sauf par un ADMIN de l'édition (ou l'opérateur), avec un motif ; le motif est journalisé
    avec le changement."""
    changing = [
        name for name in FROZEN_FIELDS if name in data and data[name] != getattr(edition, name)
    ]
    if not changing or not has_submitted_work(edition):
        return
    if _is_edition_admin(edition, actor) and reason.strip():
        return
    raise RuleViolation(
        _(
            "Réglage gelé : des soumissions existent. "
            "Seul un administrateur peut le changer, avec un motif."
        ),
        code=ErrorCode.SETTING_FROZEN,
        fields={name: [_("Gelé depuis la première soumission.")] for name in changing},
    )


@transaction.atomic
def update_edition(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor, reason: str = ""
) -> Edition:
    """Informations générales (§6.1). Un changement de fuseau ne déplace pas les instants
    UTC des dates clés : les heures locales affichées se décalent (audité, §6.2)."""
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    _writable(edition, actor)
    _check_frozen(edition, data, actor, reason)
    before = snapshot(edition)
    changed = _apply(edition, data, EDITION_INFO_FIELDS)
    if changed:
        _save(edition)
        record(
            "edition.updated",
            actor=actor,
            edition=edition,
            obj=edition,
            before={name: before[name] for name in changed},
            after={name: snapshot(edition)[name] for name in changed},
            reason=reason.strip(),
        )
    return edition


@transaction.atomic
def update_confidentiality(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor, reason: str = ""
) -> Edition:
    """Double aveugle et nombre de relecteurs : changement classé critique (§6.1).
    ``double_blind`` gelé dès la première soumission (RG-19)."""
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    _writable(edition, actor)
    _check_frozen(edition, data, actor, reason)
    before = snapshot(edition)
    changed = _apply(edition, data, CONFIDENTIALITY_FIELDS)
    if changed:
        _save(edition)
        record(
            "edition.confidentiality_changed",
            actor=actor,
            edition=edition,
            obj=edition,
            before={name: before[name] for name in changed},
            after={name: snapshot(edition)[name] for name in changed},
            reason=reason.strip(),
        )
    return edition


# --- Statut (§6.3) --------------------------------------------------------------------------

ALLOWED_TRANSITIONS: Mapping[str, frozenset[str]] = {
    EditionStatus.DRAFT: frozenset({EditionStatus.PUBLISHED}),
    EditionStatus.PUBLISHED: frozenset({EditionStatus.ARCHIVED}),
    EditionStatus.ARCHIVED: frozenset(),
}


def publication_problems(edition: Edition) -> dict[str, list[str]]:
    """Préconditions de publication : titres FR et EN (D14), dates, au moins un track et un
    type actifs, ouverture et clôture de l'appel renseignées."""
    problems: dict[str, list[str]] = {}
    if not edition.title_fr or not edition.title_en:
        problems["title_en"] = [str(_("Titres français et anglais obligatoires pour publier."))]
    if not edition.start_date or not edition.end_date:
        problems["start_date"] = [str(_("Dates de la conférence obligatoires."))]
    if not edition.tracks.filter(is_active=True).exists():
        problems["tracks"] = [str(_("Au moins une thématique active."))]
    if not edition.submission_types.filter(is_active=True).exists():
        problems["submission_types"] = [str(_("Au moins un type de communication actif."))]
    codes = set(edition.key_dates.values_list("code", flat=True))
    if not {KeyDateCode.CALL_OPEN, KeyDateCode.CALL_CLOSE} <= codes:
        problems["key_dates"] = [str(_("Ouverture et clôture de l'appel obligatoires."))]
    return problems


@transaction.atomic
def set_edition_status(
    edition: Edition, to_status: str, *, actor: Actor, reason: str = "", today: date | None = None
) -> Edition:
    """Service unique de transition du statut (règle n° 4 étendue, §5.1).

    Par commande seulement : retour en arrière, avec motif.
    """
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    if to_status not in EditionStatus.values:
        raise Invalid(fields={"status": [_("Statut inconnu.")]})
    by_command = actor.kind == ActorKind.COMMAND
    if to_status == edition.status:
        return edition
    if to_status not in ALLOWED_TRANSITIONS[edition.status]:
        if not by_command:
            raise RuleViolation(
                _("Transition de statut non autorisée."), code=ErrorCode.INVALID_TRANSITION
            )
        if not reason.strip():
            raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    if to_status == EditionStatus.PUBLISHED:
        problems = publication_problems(edition)
        if problems:
            raise RuleViolation(
                _("L'édition n'est pas prête à être publiée."),
                code=ErrorCode.EDITION_INCOMPLETE,
                fields=problems,
            )
    if (
        to_status == EditionStatus.ARCHIVED
        and not by_command
        and (edition.end_date is None or (today or timezone.localdate()) <= edition.end_date)
    ):
        raise RuleViolation(
            _("Archivage possible seulement après la fin de la conférence."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    before = snapshot(edition)
    edition.status = to_status
    now = timezone.now()
    if to_status == EditionStatus.PUBLISHED and edition.published_at is None:
        edition.published_at = now
    if to_status == EditionStatus.ARCHIVED:
        edition.archived_at = now
    edition.save(update_fields=["status", "published_at", "archived_at", "updated_at"])
    record(
        "edition.status_changed",
        actor=actor,
        edition=edition,
        obj=edition,
        before={"status": before["status"]},
        after={"status": to_status},
        reason=reason,
    )
    return edition


# --- Thématiques et types de communication ----------------------------------------------


def _create_child(
    model, edition: Edition, data: Mapping[str, Any], allowed, action: str, actor: Actor
):
    _writable(edition, actor)
    instance = model(edition=edition)
    _apply(instance, data, allowed)
    _save(instance, exclude=["edition"])
    record(action, actor=actor, edition=edition, obj=instance, after=snapshot(instance))
    return instance


def _update_child(instance, data: Mapping[str, Any], allowed, action: str, actor: Actor):
    _writable(instance.edition, actor)
    before = snapshot(instance)
    changed = _apply(instance, data, allowed)
    if changed:
        _save(instance, exclude=["edition"])
        after = snapshot(instance)
        record(
            action,
            actor=actor,
            edition=instance.edition,
            obj=instance,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return instance


def _delete_child(instance, action: str, actor: Actor) -> None:
    """Suppression : possible en L1 (aucune référence) ; à partir de L3, un élément utilisé
    renverra 409 ``in_use`` et devra être désactivé."""
    _writable(instance.edition, actor)
    record(action, actor=actor, edition=instance.edition, obj=instance, before=snapshot(instance))
    instance.delete()


@transaction.atomic
def create_track(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Track:
    return _create_child(Track, edition, data, TRACK_FIELDS, "track.created", actor)


@transaction.atomic
def update_track(track: Track, data: Mapping[str, Any], *, actor: Actor) -> Track:
    return _update_child(track, data, TRACK_FIELDS, "track.updated", actor)


@transaction.atomic
def delete_track(track: Track, *, actor: Actor) -> None:
    _delete_child(track, "track.deleted", actor)


@transaction.atomic
def create_submission_type(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor
) -> SubmissionType:
    return _create_child(
        SubmissionType, edition, data, SUBMISSION_TYPE_FIELDS, "submission_type.created", actor
    )


@transaction.atomic
def update_submission_type(
    submission_type: SubmissionType, data: Mapping[str, Any], *, actor: Actor
) -> SubmissionType:
    return _update_child(
        submission_type, data, SUBMISSION_TYPE_FIELDS, "submission_type.updated", actor
    )


@transaction.atomic
def delete_submission_type(submission_type: SubmissionType, *, actor: Actor) -> None:
    _delete_child(submission_type, "submission_type.deleted", actor)


# --- Dates clés et fuseau (D13, §6.2) ------------------------------------------------------


def local_to_utc(value: datetime, tz_name: str) -> datetime:
    """Heure locale de l'édition (sans fuseau) → instant UTC.

    Une heure inexistante (avance au printemps) ou ambiguë (recul à l'automne) est
    refusée : les deux valeurs de ``fold`` donnent alors des instants différents, ou un
    aller-retour qui ne retombe pas sur l'heure saisie.
    """
    if value.tzinfo is not None:
        raise Invalid(fields={"at_local": [_("Heure locale attendue, sans fuseau.")]})
    zone = ZoneInfo(tz_name)
    first = value.replace(tzinfo=zone, fold=0)
    second = value.replace(tzinfo=zone, fold=1)
    first_utc = first.astimezone(ZoneInfo("UTC"))
    if first_utc != second.astimezone(ZoneInfo("UTC")):
        raise Invalid(
            fields={"at_local": [_("Heure ambiguë ou inexistante (changement d'heure).")]}
        )
    if first_utc.astimezone(zone).replace(tzinfo=None) != value:
        raise Invalid(fields={"at_local": [_("Heure inexistante (changement d'heure).")]})
    return first_utc


def utc_to_local(value: datetime, tz_name: str) -> datetime:
    return value.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def check_key_date_order(edition: Edition, *, extra: KeyDate | None = None) -> None:
    """Ordre contrôlé des codes réservés (§3.4) : premier maillon strict, puis « ≤ »."""
    dates = {key_date.code: key_date.at for key_date in edition.key_dates.all()}
    if extra is not None:
        dates[extra.code] = extra.at
    _check_order_dict(dates)


def _key_date_values(data: Mapping[str, Any], edition: Edition) -> dict[str, Any]:
    values = dict(data)
    if "at_local" in values:
        values["at"] = local_to_utc(values.pop("at_local"), edition.timezone)
    return values


def _check_labels(key_date: KeyDate) -> None:
    if not key_date.is_reserved and not key_date.label_fr:
        raise Invalid(fields={"label_fr": [_("Libellé obligatoire pour un code libre.")]})


@transaction.atomic
def create_key_date(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> KeyDate:
    _writable(edition, actor)
    unknown = set(data) - set(KEY_DATE_FIELDS)
    if unknown or "at_local" not in data:
        raise Invalid(fields={"at_local": [_("Date et heure locales obligatoires.")]})
    key_date = KeyDate(edition=edition, **_key_date_values(data, edition))
    _check_labels(key_date)
    if edition.key_dates.filter(code=key_date.code).exists():
        raise Invalid(fields={"code": [_("Ce code est déjà utilisé.")]})
    check_key_date_order(edition, extra=key_date)
    _save(key_date, exclude=["edition"])
    record("key_date.created", actor=actor, edition=edition, obj=key_date, after=snapshot(key_date))
    return key_date


@transaction.atomic
def update_key_date(key_date: KeyDate, data: Mapping[str, Any], *, actor: Actor) -> KeyDate:
    edition = key_date.edition
    _writable(edition, actor)
    unknown = set(data) - set(KEY_DATE_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    before = snapshot(key_date)
    values = _key_date_values(data, edition)
    changed = [name for name, value in values.items() if getattr(key_date, name) != value]
    for name in changed:
        setattr(key_date, name, values[name])
    if not changed:
        return key_date
    _check_labels(key_date)
    others = edition.key_dates.exclude(pk=key_date.pk)
    if "code" in changed and others.filter(code=key_date.code).exists():
        raise Invalid(fields={"code": [_("Ce code est déjà utilisé.")]})
    dates = {kd.code: kd.at for kd in others}
    dates[key_date.code] = key_date.at
    _check_order_dict(dates)
    _save(key_date, exclude=["edition"])
    after = snapshot(key_date)
    record(
        "key_date.updated",
        actor=actor,
        edition=edition,
        obj=key_date,
        before={name: before[name] for name in changed if name in before},
        after={name: after[name] for name in changed if name in after},
    )
    return key_date


def _check_order_dict(dates: Mapping[str, datetime]) -> None:
    for chain in KEY_DATE_CHAINS:
        present = [(code, dates[code]) for code in chain if code in dates]
        for index in range(1, len(present)):
            (previous_code, previous), (code, current) = present[index - 1], present[index]
            strict = previous_code == chain[0]
            if current < previous or (strict and current == previous):
                raise Invalid(
                    fields={
                        "at_local": [
                            str(
                                _("%(code)s doit suivre %(previous)s.")
                                % {"code": code, "previous": previous_code}
                            )
                        ]
                    }
                )


@transaction.atomic
def delete_key_date(key_date: KeyDate, *, actor: Actor) -> None:
    _delete_child(key_date, "key_date.deleted", actor)


def key_date(edition: Edition, code: str) -> datetime | None:
    """Instant UTC d'une date clé, ``None`` si elle n'est pas renseignée."""
    return edition.key_dates.filter(code=code).values_list("at", flat=True).first()


def is_call_open(edition: Edition, now: datetime | None = None) -> bool:
    """Appel ouvert : édition publiée, entre ``call_open`` (inclus) et ``call_close`` (exclu)."""
    if edition.status != EditionStatus.PUBLISHED:
        return False
    now = now or timezone.now()
    opens, closes = (
        key_date(edition, KeyDateCode.CALL_OPEN),
        key_date(edition, KeyDateCode.CALL_CLOSE),
    )
    return opens is not None and closes is not None and opens <= now < closes


# --- Édition publique courante (§9.3) ---------------------------------------------------


def current_public_edition() -> Edition | None:
    """Édition courante publiée de la conférence (une seule conférence, hypothèse Q2)."""
    conference = (
        Conference.objects.filter(
            current_edition__isnull=False, current_edition__status=EditionStatus.PUBLISHED
        )
        .select_related("current_edition")
        .order_by("id")
        .first()
    )
    return conference.current_edition if conference is not None else None
