"""Publication du programme (plan L5 : I6, I7, I8, I11, I16 ; RG-12, RG-13, RG-17).

La publication fige le brouillon dans un **instantané** numéroté (``ProgramPublication``, en
ajout seul) : seule source du programme public (I7) et de « Mon passage » (I8). Elle est
refusée tant que le brouillon contient un conflit (I6). À ce moment seulement :

- les communications placées passent ``CONFIRMED → SCHEDULED``, celles qui ne le sont plus
  repassent ``SCHEDULED → CONFIRMED`` (par ``transition()``, règle n° 4) ;
- chaque personne dont le passage est nouveau, modifié ou supprimé reçoit un e-mail (I16),
  une fois par version.

L'instantané garde, pour « Mon passage », une **clé de personne** interne (``user:<id>`` ou
``email:<adresse>``) que les réponses publiques retirent ; il ne garde ni consigne interne
ni adresse ailleurs que dans ces clés.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Consent, ConsentKind
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import ErrorCode, RuleViolation
from apps.portal.services import public_file_url
from apps.program.models import ProgramPublication, Session
from apps.program.services import planning
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

# --- Instantané (liste blanche) ------------------------------------------------------------


def _iso(value) -> str:
    return value.isoformat()


def _consents(user_ids: set[int]) -> dict[tuple[int, str], bool]:
    """Consentements d'annuaire et de photo (L2, E12) : le dernier enregistré fait foi."""
    consents: dict[tuple[int, str], bool] = {}
    for consent in Consent.objects.filter(
        user_id__in=user_ids,
        kind__in=(ConsentKind.DIRECTORY_LISTING, ConsentKind.PHOTO_PUBLICATION),
    ).order_by("recorded_at", "id"):
        consents[(consent.user_id, consent.kind)] = consent.granted
    return consents


def _person(user, consents: dict, *, public_profile: bool = False) -> dict[str, Any]:
    profile = getattr(user, "profile", None)
    name = " ".join(
        p for p in (getattr(profile, "first_name", ""), getattr(profile, "last_name", "")) if p
    )
    data: dict[str, Any] = {
        "key": f"user:{user.pk}",
        "name": name,
        "institution": profile.institution if profile else "",
    }
    if public_profile:
        # I11 : biographie et photo d'un intervenant invité, avec les consentements de L2.
        listed = consents.get((user.pk, ConsentKind.DIRECTORY_LISTING), False)
        photo = profile.photo if profile else None
        data["bio"] = profile.bio if profile and listed else ""
        data["photo_url"] = (
            public_file_url(photo)
            if photo is not None
            and photo.published
            and consents.get((user.pk, ConsentKind.PHOTO_PUBLICATION), False)
            else None
        )
    return data


def _submission(submission: Submission) -> dict[str, Any]:
    chosen = {author.pk for author in planning.presenters(submission)}
    kind = submission.submission_type
    return {
        "id": submission.pk,
        "reference": submission.reference,
        "title": submission.title,
        "type": {"code": kind.code, "label_fr": kind.label_fr, "label_en": kind.label_en}
        if kind
        else None,
        "authors": [
            {
                "key": planning.author_key(author),
                "name": f"{author.first_name} {author.last_name}".strip(),
                "institution": author.institution,
                "presenter": author.pk in chosen,
            }
            for author in sorted(submission.authors.all(), key=lambda item: item.position)
        ],
    }


def build_snapshot(edition: Edition, sessions: list[Session]) -> dict[str, Any]:
    speaker_ids = {
        slot.speaker_id for item in sessions for slot in item.slots.all() if slot.speaker_id
    }
    consents = _consents(speaker_ids)
    return {
        "edition": {
            "code": edition.code,
            "title_fr": edition.title_fr,
            "title_en": edition.title_en,
            "timezone": edition.timezone,
        },
        "sessions": [
            {
                "id": item.pk,
                "kind": item.kind,
                "title_fr": item.title_fr,
                "title_en": item.title_en,
                "description_fr": item.description_fr,
                "description_en": item.description_en,
                "track": {
                    "code": item.track.code,
                    "name_fr": item.track.name_fr,
                    "name_en": item.track.name_en,
                }
                if item.track
                else None,
                "room": {
                    "id": item.room.pk,
                    "name": item.room.name,
                    "is_accessible": item.room.is_accessible,
                    "access_note": item.room.access_note,
                }
                if item.room
                else None,
                "starts_at": _iso(item.starts_at),
                "ends_at": _iso(item.ends_at),
                # Consignes techniques : pour « Mon passage » seulement, jamais publiques.
                "instructions": item.instructions,
                "roles": [
                    {"role": role.role, **_person(role.user, consents)}
                    for role in sorted(item.roles.all(), key=lambda row: (row.role, row.pk))
                ],
                "slots": [
                    {
                        "id": slot.pk,
                        "position": slot.position,
                        "starts_at": _iso(slot.starts_at),
                        "ends_at": _iso(slot.ends_at),
                        "duration_min": slot.duration_min,
                        "submission": _submission(slot.submission) if slot.submission else None,
                        "title_fr": slot.title_fr,
                        "title_en": slot.title_en,
                        "speaker": _person(slot.speaker, consents, public_profile=True)
                        if slot.speaker
                        else None,
                    }
                    for slot in sorted(item.slots.all(), key=lambda row: (row.position, row.pk))
                ],
            }
            for item in sessions
        ],
    }


# --- Passages et différences (I8, I16) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Passage:
    """Passage d'une personne : rôle, session, créneau éventuel, horaire, salle, titre."""

    role: str  # presenter, speaker, chair, discussant, moderator, panelist
    session: int
    slot: int | None
    starts_at: str
    ends_at: str
    room: str
    title: str  # titre de la communication ou de l'élément ; sinon de la session
    reference: str


def passages(snapshot: dict[str, Any]) -> dict[str, list[Passage]]:
    """Passages de chaque personne (clé interne) dans un instantané."""
    result: dict[str, list[Passage]] = defaultdict(list)
    for item in snapshot.get("sessions", []):
        room = (item.get("room") or {}).get("name", "")
        for role in item.get("roles", []):
            result[role["key"]].append(
                Passage(
                    role["role"],
                    item["id"],
                    None,
                    item["starts_at"],
                    item["ends_at"],
                    room,
                    item["title_fr"],
                    "",
                )
            )
        for slot in item.get("slots", []):
            submission = slot.get("submission")
            if slot.get("speaker"):
                result[slot["speaker"]["key"]].append(
                    Passage(
                        "speaker",
                        item["id"],
                        slot["id"],
                        slot["starts_at"],
                        slot["ends_at"],
                        room,
                        slot["title_fr"],
                        "",
                    )
                )
            if submission:
                for author in submission["authors"]:
                    if author["presenter"]:
                        result[author["key"]].append(
                            Passage(
                                "presenter",
                                item["id"],
                                slot["id"],
                                slot["starts_at"],
                                slot["ends_at"],
                                room,
                                submission["title"],
                                submission["reference"] or "",
                            )
                        )
    return result


def diff_passages(
    old: dict[str, Any] | None, new: dict[str, Any]
) -> dict[str, tuple[str, list[Passage]]]:
    """Personnes dont le passage change entre deux instantanés : ``added``, ``changed`` ou
    ``removed``, avec les passages nouveaux (ou anciens, s'ils sont supprimés)."""
    before = passages(old) if old else {}
    after = passages(new)
    changes: dict[str, tuple[str, list[Passage]]] = {}
    for key in before.keys() | after.keys():
        previous = sorted(before.get(key, []), key=lambda p: (p.starts_at, p.session))
        current = sorted(after.get(key, []), key=lambda p: (p.starts_at, p.session))
        if previous == current:
            continue
        if not previous:
            changes[key] = ("added", current)
        elif not current:
            changes[key] = ("removed", previous)
        else:
            changes[key] = ("changed", current)
    return changes


def _session_summary(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, int]:
    def index(snapshot):
        return {item["id"]: item for item in (snapshot or {}).get("sessions", [])}

    before, after = index(old), index(new)
    return {
        "added": len(after.keys() - before.keys()),
        "removed": len(before.keys() - after.keys()),
        "changed": sum(1 for key in after.keys() & before.keys() if after[key] != before[key]),
    }


# --- Publication (I6) ----------------------------------------------------------------------


def latest_publication(edition: Edition) -> ProgramPublication | None:
    return ProgramPublication.objects.filter(edition=edition).order_by("-version").first()


def _placed_ids(snapshot: dict[str, Any]) -> set[int]:
    return {
        slot["submission"]["id"]
        for item in snapshot["sessions"]
        for slot in item["slots"]
        if slot.get("submission")
    }


@transaction.atomic
def publish_program(
    edition: Edition, *, actor: Actor, revision: int | None = None
) -> ProgramPublication:
    """Publie le brouillon (I6) : refus tant qu'il reste un conflit (RG-12, RG-13) ou si rien
    n'a changé ; transitions et e-mails à ce moment seulement."""
    from apps.program.notifications import passage_changed

    state = planning.begin_write(edition, actor, revision)
    sessions = list(planning.program_sessions(edition))
    conflicts = planning.detect_conflicts(edition, sessions)
    if conflicts:
        raise RuleViolation(
            _("Le programme contient des conflits : corrigez-les avant de publier."),
            code=ErrorCode.PROGRAM_CONFLICTS,
            fields={"conflicts": [str(len(conflicts))]},
        )
    if state.published_version and state.revision == state.published_revision:
        raise RuleViolation(
            _("Aucune modification depuis la dernière publication."),
            code=ErrorCode.PROGRAM_UNCHANGED,
        )
    previous = latest_publication(edition)
    snapshot = build_snapshot(edition, sessions)
    changes = diff_passages(previous.snapshot if previous else None, snapshot)
    now = timezone.now()
    version = state.published_version + 1
    summary = {
        "sessions": _session_summary(previous.snapshot if previous else None, snapshot),
        "people": {
            status: sum(1 for kind, _items in changes.values() if kind == status)
            for status in ("added", "changed", "removed")
        },
    }
    publication = ProgramPublication.objects.create(
        edition=edition,
        version=version,
        revision=state.revision,
        published_at=now,
        published_by=actor.user,
        snapshot=snapshot,
        summary=summary,
    )
    state.published_revision = state.revision
    state.published_version = version
    state.save(update_fields=["published_revision", "published_version"])

    placed = _placed_ids(snapshot)
    for submission in Submission.objects.filter(
        edition=edition, status__in=(S.CONFIRMED, S.SCHEDULED)
    ).order_by("pk"):
        if submission.status == S.CONFIRMED and submission.pk in placed:
            workflow.transition(submission, S.SCHEDULED, actor)
        elif submission.status == S.SCHEDULED and submission.pk not in placed:
            workflow.transition(
                submission, S.CONFIRMED, actor, reason="Retirée du programme publié."
            )

    record(
        "program.published",
        actor=actor,
        edition=edition,
        obj=publication,
        after={"version": version, "revision": state.revision, **summary},
    )
    for key, (status, items) in sorted(changes.items()):
        passage_changed(edition, publication, key, status, items)
    return publication


def published_slot(found: ProgramPublication | None, submission_id: int) -> dict[str, Any] | None:
    """Créneau d'une communication dans une publication (plan L5 §4), ou ``None``."""
    if found is None:
        return None
    for item in found.snapshot["sessions"]:
        for slot in item["slots"]:
            if (slot.get("submission") or {}).get("id") == submission_id:
                return {
                    "version": found.version,
                    "session_id": item["id"],
                    "session_title_fr": item["title_fr"],
                    "session_title_en": item["title_en"],
                    "room": item["room"]["name"] if item["room"] else None,
                    # Instants de l'instantané relus en dates : format de l'API (« Z »).
                    "starts_at": dt.datetime.fromisoformat(slot["starts_at"]),
                    "ends_at": dt.datetime.fromisoformat(slot["ends_at"]),
                }
    return None


def public_paths(edition: Edition) -> list[dict[str, str]]:
    """Adresses du programme public (I7), d'après la dernière publication : une page par jour
    (heure de l'édition) et une par session, en FR et en EN. Aucune avant publication."""
    from apps.portal.site import SITE_ROUTES, site_page_path
    from apps.program.serializers import local_day

    found = latest_publication(edition)
    if found is None:
        return []
    base = {lang: site_page_path(SITE_ROUTES["program"], lang) for lang in ("fr", "en")}
    zone = found.snapshot["edition"]["timezone"]
    sessions = found.snapshot["sessions"]
    days = sorted({local_day(item["starts_at"], zone) for item in sessions})
    return [{lang: f"{base[lang]}{day}/" for lang in base} for day in days] + [
        {lang: f"{base[lang]}session/{item['id']}/" for lang in base}
        for item in sorted(sessions, key=lambda row: row["id"])
    ]


def person_hash(key: str) -> str:
    """Empreinte d'une clé de personne (clés d'idempotence sans adresse en clair)."""
    return hashlib.sha256(key.encode()).hexdigest()[:24]
