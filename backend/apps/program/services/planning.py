"""Planification du programme (plan L5 : I2 à I5, I9, I10, I12 à I14 ; RG-12, RG-13).

**Service unique** pour toutes les écritures du brouillon : salles, sessions, créneaux, rôles
de séance. Chaque écriture :

1. vérifie que l'édition est modifiable (archivée : 409) ;
2. verrouille la ligne ``ProgramState`` de l'édition, ce qui met en série les écritures et
   les contrôles de conflits (MariaDB n'a pas de contrainte d'exclusion de plages, §8.2) ;
3. compare la révision attendue (``If-Match``) à la révision courante : 412 sinon (I14) ;
4. recalcule les créneaux des sessions touchées (I3) ;
5. journalise (RG-17) et incrémente la révision.

Le brouillon **peut** contenir des conflits (I6) : ils sont signalés par ``detect_conflicts``
après chaque écriture, et la publication (L5.4) est refusée tant qu'il en reste.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services.invitations import display_name
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, Track
from apps.conferences.services import local_to_utc
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation, StaleRevision
from apps.program.models import (
    Equipment,
    ProgramState,
    Room,
    Session,
    SessionKind,
    SessionRole,
    SessionRoleKind,
    Slot,
)
from apps.submissions.models import Submission, SubmissionAuthor
from apps.submissions.models import SubmissionStatus as S

# Communications programmables (I5) : confirmées, ou déjà programmées (déplacement).
PROGRAMMABLE = (S.CONFIRMED, S.SCHEDULED)
# Durée d'un créneau quand le type de communication n'en propose pas (I3).
DEFAULT_SLOT_MINUTES = 20
# Une session dure au plus une journée (dîner de gala jusqu'après minuit compris).
MAX_SESSION = dt.timedelta(hours=24)

ROOM_FIELDS = (
    "name",
    "capacity",
    "equipment",
    "note",
    "is_accessible",
    "access_note",
    "is_active",
    "position",
)
SESSION_FIELDS = (
    "kind",
    "title_fr",
    "title_en",
    "description_fr",
    "description_en",
    "track",
    "room",
    "starts_local",
    "ends_local",
    "instructions",
)


# --- Verrou, révision, journal ---------------------------------------------------------------


def _writable(edition: Edition, actor: Actor) -> None:
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)


def program_state(edition: Edition, *, lock: bool = False) -> ProgramState:
    """Ligne d'état du programme de l'édition, créée au besoin ; verrouillée sur demande."""
    try:
        with transaction.atomic():
            state, _created = ProgramState.objects.get_or_create(edition=edition)
    except IntegrityError:  # création concurrente : l'autre transaction l'a créée
        state = ProgramState.objects.get(edition=edition)
    if lock:
        state = ProgramState.objects.select_for_update().get(pk=state.pk)
    return state


def begin_write(edition: Edition, actor: Actor, revision: int | None) -> ProgramState:
    """Début de toute écriture : édition modifiable, verrou, révision attendue (I14)."""
    _writable(edition, actor)
    state = program_state(edition, lock=True)
    if revision is not None and revision != state.revision:
        raise StaleRevision()
    return state


def _bump(state: ProgramState) -> None:
    state.revision += 1
    state.save(update_fields=["revision"])


def mark_changed(edition: Edition) -> None:
    """Le brouillon dépend d'une donnée modifiée ailleurs (présentateurs d'une communication
    placée, RG-12) : nouvelle révision, pour que les planificateurs rechargent (I14)."""
    _bump(program_state(edition, lock=True))


def _audit(action: str, *, actor: Actor, edition: Edition, obj: Any, before=None, after=None):
    record(f"program.{action}", actor=actor, edition=edition, obj=obj, before=before, after=after)


def _changes(before: Mapping[str, Any], after: Mapping[str, Any]) -> tuple[dict, dict]:
    changed = [name for name in after if before.get(name) != after[name]]
    return {name: before.get(name) for name in changed}, {name: after[name] for name in changed}


# --- Salles (I9) ---------------------------------------------------------------------------


def _clean_room(edition: Edition, data: Mapping[str, Any], room: Room | None) -> dict[str, Any]:
    unknown = set(data) - set(ROOM_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    values = dict(data)
    if "name" in values:
        values["name"] = str(values["name"]).strip()
        if not values["name"]:
            raise Invalid(fields={"name": [_("Nom obligatoire.")]})
        duplicate = Room.objects.filter(edition=edition, name__iexact=values["name"])
        if room is not None:
            duplicate = duplicate.exclude(pk=room.pk)
        if duplicate.exists():
            raise Invalid(fields={"name": [_("Une salle porte déjà ce nom.")]})
    if "equipment" in values:
        equipment = values["equipment"] or []
        if not isinstance(equipment, list) or any(
            item not in Equipment.values for item in equipment
        ):
            raise Invalid(fields={"equipment": [_("Équipement inconnu.")]})
        values["equipment"] = sorted(set(equipment), key=Equipment.values.index)
    return values


@transaction.atomic
def create_room(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor, revision: int | None = None
) -> Room:
    state = begin_write(edition, actor, revision)
    values = _clean_room(edition, data, None)
    if "name" not in values:
        raise Invalid(fields={"name": [_("Nom obligatoire.")]})
    room = Room(edition=edition, **values)
    room.full_clean()
    room.save()
    _audit("room_created", actor=actor, edition=edition, obj=room, after=snapshot(room))
    _bump(state)
    return room


@transaction.atomic
def update_room(
    room: Room, data: Mapping[str, Any], *, actor: Actor, revision: int | None = None
) -> Room:
    state = begin_write(room.edition, actor, revision)
    room = Room.objects.select_for_update().get(pk=room.pk)
    values = _clean_room(room.edition, data, room)
    before = snapshot(room)
    for name, value in values.items():
        setattr(room, name, value)
    room.full_clean()
    room.save()
    old, new = _changes(before, snapshot(room))
    if new:
        _audit("room_updated", actor=actor, edition=room.edition, obj=room, before=old, after=new)
        _bump(state)
    return room


@transaction.atomic
def delete_room(room: Room, *, actor: Actor, revision: int | None = None) -> None:
    """Une salle utilisée ne se supprime pas (409 ``in_use``) : on la désactive (I9)."""
    state = begin_write(room.edition, actor, revision)
    if Session.objects.filter(room=room).exists():
        raise RuleViolation(
            _("Salle utilisée par une session : désactivez-la plutôt."), code=ErrorCode.IN_USE
        )
    _audit("room_deleted", actor=actor, edition=room.edition, obj=room, before=snapshot(room))
    room.delete()
    _bump(state)


# --- Sessions (I2, I12) --------------------------------------------------------------------


def _local(value: Any, edition: Edition, field: str) -> dt.datetime:
    """Heure locale de l'édition (D13) → UTC ; erreurs renvoyées sur le champ de la session."""
    if not isinstance(value, dt.datetime):
        raise Invalid(fields={field: [_("Date et heure locales attendues.")]})
    try:
        return local_to_utc(value, edition.timezone)
    except Invalid as error:
        raise Invalid(fields={field: error.fields.get("at_local", [])}) from error


def _check_window(edition: Edition, starts_at: dt.datetime, ends_at: dt.datetime) -> None:
    """Fin après le début, durée d'une journée au plus, début dans les dates de l'édition."""
    if ends_at <= starts_at:
        raise Invalid(fields={"ends_local": [_("La fin doit suivre le début.")]})
    if ends_at - starts_at > MAX_SESSION:
        raise Invalid(fields={"ends_local": [_("Une session dure au plus 24 heures.")]})
    first, last = edition.start_date, edition.end_date
    if first and last:
        day = starts_at.astimezone(ZoneInfo(edition.timezone)).date()
        if not first <= day <= last:
            raise Invalid(
                fields={"starts_local": [_("La session doit se tenir pendant l'édition.")]}
            )


def _clean_session(
    edition: Edition, data: Mapping[str, Any], session: Session | None
) -> dict[str, Any]:
    unknown = set(data) - set(SESSION_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    values = {
        name: value for name, value in data.items() if name not in ("starts_local", "ends_local")
    }
    if "kind" in values and values["kind"] not in SessionKind.values:
        raise Invalid(fields={"kind": [_("Type de session inconnu.")]})
    if "title_fr" in values and not str(values["title_fr"]).strip():
        raise Invalid(fields={"title_fr": [_("Titre français obligatoire.")]})
    if values.get("room") is not None:
        if not isinstance(values["room"], Room):
            raise Invalid(fields={"room": [_("Salle d'une autre édition.")]})
        room = values["room"] = Room.objects.filter(pk=values["room"].pk).first()
        if room is None or room.edition_id != edition.pk:
            raise Invalid(fields={"room": [_("Salle d'une autre édition.")]})
        if not room.is_active and (session is None or session.room_id != room.pk):
            raise Invalid(fields={"room": [_("Salle désactivée.")]})
    if values.get("track") is not None:
        track = values["track"]
        if not isinstance(track, Track) or track.edition_id != edition.pk:
            raise Invalid(fields={"track": [_("Thématique d'une autre édition.")]})
    if "starts_local" in data:
        values["starts_at"] = _local(data["starts_local"], edition, "starts_local")
    if "ends_local" in data:
        values["ends_at"] = _local(data["ends_local"], edition, "ends_local")
    return values


@transaction.atomic
def create_session(
    edition: Edition, data: Mapping[str, Any], *, actor: Actor, revision: int | None = None
) -> Session:
    state = begin_write(edition, actor, revision)
    for name in ("kind", "title_fr", "starts_local", "ends_local"):
        if name not in data:
            raise Invalid(fields={name: [_("Champ obligatoire.")]})
    values = _clean_session(edition, data, None)
    _check_window(edition, values["starts_at"], values["ends_at"])
    session = Session(edition=edition, **values)
    session.full_clean()
    session.save()
    _audit("session_created", actor=actor, edition=edition, obj=session, after=snapshot(session))
    _bump(state)
    return session


@transaction.atomic
def update_session(
    session: Session, data: Mapping[str, Any], *, actor: Actor, revision: int | None = None
) -> Session:
    """Un changement d'horaire recalcule les créneaux (I3) ; la durée réelle compte (I12)."""
    edition = session.edition
    state = begin_write(edition, actor, revision)
    session = Session.objects.select_for_update().get(pk=session.pk)
    values = _clean_session(edition, data, session)
    before = snapshot(session)
    for name, value in values.items():
        setattr(session, name, value)
    _check_window(edition, session.starts_at, session.ends_at)
    session.full_clean()
    session.save()
    old, new = _changes(before, snapshot(session))
    if new:
        if "starts_at" in new:
            reflow(session)
        _audit("session_updated", actor=actor, edition=edition, obj=session, before=old, after=new)
        _bump(state)
    return session


@transaction.atomic
def delete_session(session: Session, *, actor: Actor, revision: int | None = None) -> None:
    """Supprime la session, ses créneaux et ses rôles : les communications retournent dans
    la liste « à programmer » (journalisé)."""
    edition = session.edition
    state = begin_write(edition, actor, revision)
    slots = list(session.slots.values_list("submission__reference", flat=True))
    _audit(
        "session_deleted",
        actor=actor,
        edition=edition,
        obj=session,
        before={**snapshot(session), "submissions": [ref for ref in slots if ref]},
    )
    session.slots.all().delete()
    session.roles.all().delete()
    session.delete()
    _bump(state)


# --- Créneaux (I3, RG-13) ------------------------------------------------------------------


def reflow(session: Session) -> None:
    """Recalcule positions, débuts et fins des créneaux d'une session : à la suite depuis le
    début de la session, séparés par le tampon de l'édition (RG-13). Temps réel, en UTC
    (I12). Le dépassement éventuel est signalé par ``detect_conflicts``, pas refusé."""
    buffer = dt.timedelta(minutes=session.edition.session_buffer_minutes)
    cursor = session.starts_at
    changed = []
    for index, slot in enumerate(session.slots.order_by("position", "id")):
        if index:
            cursor += buffer
        starts_at, ends_at = cursor, cursor + dt.timedelta(minutes=slot.duration_min)
        if (slot.position, slot.starts_at, slot.ends_at) != (index, starts_at, ends_at):
            slot.position, slot.starts_at, slot.ends_at = index, starts_at, ends_at
            changed.append(slot)
        cursor = ends_at
    if changed:
        Slot.objects.bulk_update(changed, ["position", "starts_at", "ends_at"])


def _insert_at(session: Session, slot: Slot, position: int | None) -> None:
    """Range le créneau à ``position`` (fin de session par défaut) et décale les suivants."""
    others = [item for item in session.slots.order_by("position", "id") if item.pk != slot.pk]
    index = len(others) if position is None else max(0, min(position, len(others)))
    others.insert(index, slot)
    for rank, item in enumerate(others):
        item.position = rank
    Slot.objects.bulk_update(others, ["position"])


def _duration(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 600:
        raise Invalid(fields={"duration_min": [_("Durée de 1 à 600 minutes.")]})
    return value


def _locked_session(session: Session) -> Session:
    return Session.objects.select_for_update().select_related("edition").get(pk=session.pk)


@transaction.atomic
def place_submission(
    session: Session,
    submission: Submission,
    *,
    actor: Actor,
    revision: int | None = None,
    position: int | None = None,
    duration_min: int | None = None,
) -> Slot:
    """Place une communication confirmée (I5) dans une session. Une communication déjà
    placée se déplace par ``move_slot``."""
    edition = session.edition
    state = begin_write(edition, actor, revision)
    session = _locked_session(session)
    submission = Submission.objects.select_for_update().get(pk=submission.pk)
    if submission.edition_id != edition.pk:
        raise Invalid(fields={"submission": [_("Communication d'une autre édition.")]})
    if submission.status not in PROGRAMMABLE:
        raise RuleViolation(
            _("Seule une communication confirmée se programme."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    if Slot.objects.filter(submission=submission).exists():
        raise Invalid(fields={"submission": [_("Communication déjà programmée : déplacez-la.")]})
    if duration_min is None:
        kind = submission.submission_type
        duration_min = (kind.default_duration_min if kind else None) or DEFAULT_SLOT_MINUTES
    slot = Slot(
        session=session,
        submission=submission,
        duration_min=_duration(duration_min),
        position=0,
        starts_at=session.starts_at,
        ends_at=session.starts_at + dt.timedelta(minutes=duration_min),
    )
    slot.save()
    _insert_at(session, slot, position)
    reflow(session)
    slot.refresh_from_db()
    _audit("slot_placed", actor=actor, edition=edition, obj=slot, after=snapshot(slot))
    _bump(state)
    return slot


def _clean_speaker(edition: Edition, speaker: Any) -> User | None:
    if speaker is None:
        return None
    if not isinstance(speaker, User) or speaker.anonymized_at is not None:
        raise Invalid(fields={"speaker": [_("Intervenant inconnu.")]})
    return speaker


@transaction.atomic
def add_free_slot(
    session: Session,
    *,
    title_fr: str,
    actor: Actor,
    revision: int | None = None,
    title_en: str = "",
    speaker: User | None = None,
    duration_min: int = DEFAULT_SLOT_MINUTES,
    position: int | None = None,
) -> Slot:
    """Élément libre (I3) : conférence invitée, discours, remise de prix… avec ou sans
    intervenant invité (I11)."""
    edition = session.edition
    state = begin_write(edition, actor, revision)
    session = _locked_session(session)
    if not title_fr.strip():
        raise Invalid(fields={"title_fr": [_("Titre français obligatoire.")]})
    duration_min = _duration(duration_min)
    slot = Slot(
        session=session,
        title_fr=title_fr.strip(),
        title_en=title_en.strip(),
        speaker=_clean_speaker(edition, speaker),
        duration_min=duration_min,
        position=0,
        starts_at=session.starts_at,
        ends_at=session.starts_at + dt.timedelta(minutes=duration_min),
    )
    slot.save()
    _insert_at(session, slot, position)
    reflow(session)
    slot.refresh_from_db()
    _audit("slot_added", actor=actor, edition=edition, obj=slot, after=snapshot(slot))
    _bump(state)
    return slot


@transaction.atomic
def move_slot(
    slot: Slot,
    *,
    actor: Actor,
    revision: int | None = None,
    session: Session | None = None,
    position: int | None = None,
) -> Slot:
    """Déplace un créneau dans sa session ou vers une autre session de l'édition."""
    edition = slot.session.edition
    state = begin_write(edition, actor, revision)
    slot = Slot.objects.select_for_update().select_related("session").get(pk=slot.pk)
    source = _locked_session(slot.session)
    target = source if session is None else _locked_session(session)
    if target.edition_id != edition.pk:
        raise Invalid(fields={"session": [_("Session d'une autre édition.")]})
    before = snapshot(slot)
    if target.pk != source.pk:
        slot.session = target
        slot.save(update_fields=["session", "updated_at"])
    _insert_at(target, slot, position)
    if target.pk != source.pk:
        _compact(source)
        reflow(source)
    reflow(target)
    slot.refresh_from_db()
    old, new = _changes(before, snapshot(slot))
    if new:
        _audit("slot_moved", actor=actor, edition=edition, obj=slot, before=old, after=new)
        _bump(state)
    return slot


def _compact(session: Session) -> None:
    slots = list(session.slots.order_by("position", "id"))
    for rank, item in enumerate(slots):
        item.position = rank
    Slot.objects.bulk_update(slots, ["position"])


@transaction.atomic
def update_slot(
    slot: Slot,
    data: Mapping[str, Any],
    *,
    actor: Actor,
    revision: int | None = None,
) -> Slot:
    """Durée, et pour un élément libre : titres et intervenant invité."""
    edition = slot.session.edition
    state = begin_write(edition, actor, revision)
    slot = Slot.objects.select_for_update().select_related("session").get(pk=slot.pk)
    allowed = {"duration_min"} | (
        set() if slot.submission_id else {"title_fr", "title_en", "speaker"}
    )
    unknown = set(data) - allowed
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    before = snapshot(slot)
    if "duration_min" in data:
        slot.duration_min = _duration(data["duration_min"])
    if "title_fr" in data:
        if not str(data["title_fr"]).strip():
            raise Invalid(fields={"title_fr": [_("Titre français obligatoire.")]})
        slot.title_fr = str(data["title_fr"]).strip()
    if "title_en" in data:
        slot.title_en = str(data["title_en"]).strip()
    if "speaker" in data:
        slot.speaker = _clean_speaker(edition, data["speaker"])
    slot.save()
    reflow(_locked_session(slot.session))
    slot.refresh_from_db()
    old, new = _changes(before, snapshot(slot))
    if new:
        _audit("slot_updated", actor=actor, edition=edition, obj=slot, before=old, after=new)
        _bump(state)
    return slot


@transaction.atomic
def remove_slot(slot: Slot, *, actor: Actor, revision: int | None = None) -> None:
    """Retire le créneau ; la communication retourne dans la liste « à programmer »."""
    edition = slot.session.edition
    state = begin_write(edition, actor, revision)
    slot = Slot.objects.select_for_update().select_related("session").get(pk=slot.pk)
    session = _locked_session(slot.session)
    _audit("slot_removed", actor=actor, edition=edition, obj=slot, before=snapshot(slot))
    slot.delete()
    _compact(session)
    reflow(session)
    _bump(state)


# --- Rôles de séance (I10) -----------------------------------------------------------------


@transaction.atomic
def add_session_role(
    session: Session,
    user: User,
    role: str,
    *,
    actor: Actor,
    revision: int | None = None,
) -> SessionRole:
    edition = session.edition
    state = begin_write(edition, actor, revision)
    if role not in SessionRoleKind.values:
        raise Invalid(fields={"role": [_("Rôle de séance inconnu.")]})
    if user.anonymized_at is not None or not user.is_active:
        raise Invalid(fields={"user": [_("Personne inconnue.")]})
    if SessionRole.objects.filter(session=session, user=user, role=role).exists():
        raise Invalid(fields={"user": [_("Cette personne a déjà ce rôle dans la session.")]})
    item = SessionRole.objects.create(session=session, user=user, role=role)
    _audit("role_added", actor=actor, edition=edition, obj=item, after=snapshot(item))
    _bump(state)
    return item


@transaction.atomic
def remove_session_role(item: SessionRole, *, actor: Actor, revision: int | None = None) -> None:
    edition = item.session.edition
    state = begin_write(edition, actor, revision)
    _audit("role_removed", actor=actor, edition=edition, obj=item, before=snapshot(item))
    item.delete()
    _bump(state)


# --- Conflits (RG-12, RG-13) ---------------------------------------------------------------


class ConflictType:
    ROOM = "room"  # RG-12 : deux sessions dans la même salle au même moment
    PERSON = "person"  # RG-12 : une personne à deux endroits au même moment
    OVERFLOW = "overflow"  # RG-13 : créneaux et tampons au-delà de la fin de la session


@dataclass(frozen=True, slots=True)
class ProgramConflict:
    """Conflit du brouillon. ``person`` : nom affiché, jamais d'adresse."""

    kind: str
    sessions: tuple[int, ...]
    slots: tuple[int, ...] = ()
    person: str = ""
    minutes: int = 0


@dataclass(frozen=True, slots=True)
class _Presence:
    key: str
    label: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    session: int
    slot: int | None


def author_key(author: SubmissionAuthor) -> str:
    """Clé de personne d'un auteur : son compte, sinon son adresse (RG-12, I8)."""
    return f"user:{author.user_id}" if author.user_id else f"email:{author.email.strip().lower()}"


def presenters(submission: Submission) -> list[SubmissionAuthor]:
    """Présentateurs d'une communication : ceux de la confirmation (I5), sinon les auteurs
    marqués présentateurs, sinon l'auteur qui a soumis."""
    authors = sorted(submission.authors.all(), key=lambda author: author.position)
    confirmation = getattr(submission, "presentation_confirmation", None)
    if confirmation is not None and confirmation.presenters:
        chosen = [author for author in authors if author.position in confirmation.presenters]
        if chosen:
            return chosen
    flagged = [author for author in authors if author.is_presenter]
    if flagged:
        return flagged
    return [author for author in authors if author.user_id == submission.submitter_id][:1]


def _presences(sessions: Iterable[Session]) -> list[_Presence]:
    presences: list[_Presence] = []
    for session in sessions:
        for item in session.roles.all():
            presences.append(
                _Presence(
                    f"user:{item.user_id}",
                    display_name(item.user),
                    session.starts_at,
                    session.ends_at,
                    session.pk,
                    None,
                )
            )
        for slot in session.slots.all():
            if slot.speaker_id:
                presences.append(
                    _Presence(
                        f"user:{slot.speaker_id}",
                        display_name(slot.speaker),
                        slot.starts_at,
                        slot.ends_at,
                        session.pk,
                        slot.pk,
                    )
                )
            if slot.submission_id:
                for author in presenters(slot.submission):
                    presences.append(
                        _Presence(
                            author_key(author),
                            f"{author.first_name} {author.last_name}".strip(),
                            slot.starts_at,
                            slot.ends_at,
                            session.pk,
                            slot.pk,
                        )
                    )
    return presences


def program_sessions(edition: Edition):
    """Sessions du brouillon, avec tout ce que demandent conflits et instantanés (requêtes en
    nombre constant)."""
    return (
        Session.objects.filter(edition=edition)
        .select_related("room", "track")
        .prefetch_related(
            Prefetch("roles", queryset=SessionRole.objects.select_related("user__profile")),
            Prefetch(
                "slots",
                queryset=Slot.objects.select_related(
                    "speaker__profile",
                    "submission__submission_type",
                    "submission__presentation_confirmation",
                ).prefetch_related("submission__authors"),
            ),
        )
        .order_by("starts_at", "room__position", "id")
    )


def detect_conflicts(
    edition: Edition, sessions: list[Session] | None = None
) -> list[ProgramConflict]:
    """Analyse complète du brouillon : salles (RG-12), personnes (RG-12), dépassements
    (RG-13). Une personne présente deux fois dans la **même** session n'est pas en conflit
    (président qui présente dans sa séance)."""
    sessions = list(program_sessions(edition)) if sessions is None else sessions
    conflicts: list[ProgramConflict] = []

    by_room: dict[int, list[Session]] = defaultdict(list)
    for session in sessions:
        if session.room_id:
            by_room[session.room_id].append(session)
    for items in by_room.values():
        items.sort(key=lambda item: item.starts_at)
        for index, first in enumerate(items):
            for second in items[index + 1 :]:
                if second.starts_at >= first.ends_at:
                    break
                conflicts.append(ProgramConflict(ConflictType.ROOM, (first.pk, second.pk)))

    for session in sessions:
        slots = sorted(session.slots.all(), key=lambda slot: slot.position)
        if slots and slots[-1].ends_at > session.ends_at:
            over = slots[-1].ends_at - session.ends_at
            conflicts.append(
                ProgramConflict(
                    ConflictType.OVERFLOW, (session.pk,), minutes=int(over.total_seconds() // 60)
                )
            )

    by_person: dict[str, list[_Presence]] = defaultdict(list)
    for presence in _presences(sessions):
        by_person[presence.key].append(presence)
    for items in by_person.values():
        items.sort(key=lambda item: item.starts_at)
        seen: set[tuple[int, int]] = set()
        for index, first in enumerate(items):
            for second in items[index + 1 :]:
                if second.starts_at >= first.ends_at:
                    break
                if second.session == first.session:
                    continue
                pair = tuple(sorted((first.session, second.session)))
                if pair in seen:
                    continue
                seen.add(pair)
                conflicts.append(
                    ProgramConflict(
                        ConflictType.PERSON,
                        pair,
                        tuple(slot for slot in (first.slot, second.slot) if slot),
                        person=first.label,
                    )
                )
    return conflicts


def to_schedule(edition: Edition):
    """Communications confirmées pas encore placées (liste « à programmer », §5.4)."""
    return (
        Submission.objects.filter(
            edition=edition, status__in=PROGRAMMABLE, program_slot__isnull=True
        )
        .select_related("track", "submission_type", "presentation_confirmation")
        .prefetch_related("authors")
        .order_by("reference")
    )
