"""« Mon passage » (plan L5, I8 ; étude M7, agenda par acteur).

Lu dans la **dernière publication** de chaque édition non archivée, jamais dans le
brouillon. Une personne s'y reconnaît par son compte (``user:<id>``) ou par l'une de ses
adresses vérifiées (``email:<adresse>``, co-auteur qui n'avait pas de compte à la
soumission). Chaque passage donne : date, heure (fuseau de l'édition), salle, durée, rôle,
co-intervenants de la session, consignes.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlparse

from allauth.account.models import EmailAddress
from django.conf import settings
from django.db.models import Max

from apps.conferences.models import EditionStatus
from apps.program import ical
from apps.program.models import ProgramPublication
from apps.program.services.publication import passages


def person_keys(user) -> set[str]:
    keys = {f"user:{user.pk}"}
    for address in EmailAddress.objects.filter(user=user, verified=True).values_list(
        "email", flat=True
    ):
        keys.add(f"email:{address.strip().lower()}")
    return keys


def _latest_publications():
    latest = (
        ProgramPublication.objects.exclude(edition__status=EditionStatus.ARCHIVED)
        .values("edition_id")
        .annotate(version=Max("version"))
    )
    wanted = {(row["edition_id"], row["version"]) for row in latest}
    rows = ProgramPublication.objects.filter(
        edition_id__in={edition for edition, _version in wanted}
    ).select_related("edition")
    return [row for row in rows if (row.edition_id, row.version) in wanted]


def _names(session: dict[str, Any], keys: set[str]) -> tuple[list[str], list[str]]:
    """Co-intervenants (présentateurs, intervenants, rôles autres que président) et
    présidents de séance de la session, sans la personne elle-même."""
    others: list[str] = []
    chairs: list[str] = []
    for role in session.get("roles", []):
        if role["key"] in keys:
            continue
        (chairs if role["role"] == "chair" else others).append(role["name"])
    for slot in session.get("slots", []):
        if slot.get("speaker") and slot["speaker"]["key"] not in keys:
            others.append(slot["speaker"]["name"])
        for author in (slot.get("submission") or {}).get("authors", []):
            if author["presenter"] and author["key"] not in keys:
                others.append(author["name"])
    return sorted(set(others)), sorted(set(chairs))


def my_agenda(user) -> list[dict[str, Any]]:
    keys = person_keys(user)
    entries: list[dict[str, Any]] = []
    for publication in _latest_publications():
        snapshot = publication.snapshot
        sessions = {item["id"]: item for item in snapshot.get("sessions", [])}
        index = passages(snapshot)
        found = {passage for key in keys for passage in index.get(key, [])}
        for passage in found:
            session = sessions[passage.session]
            slot = next((item for item in session["slots"] if item["id"] == passage.slot), None)
            others, chairs = _names(session, keys)
            room = session.get("room") or {}
            starts = dt.datetime.fromisoformat(passage.starts_at)
            ends = dt.datetime.fromisoformat(passage.ends_at)
            entries.append(
                {
                    "edition": {
                        "code": snapshot["edition"]["code"],
                        "title_fr": snapshot["edition"]["title_fr"],
                        "title_en": snapshot["edition"]["title_en"],
                        "timezone": snapshot["edition"]["timezone"],
                    },
                    "version": publication.version,
                    "role": passage.role,
                    "session": {
                        "id": session["id"],
                        "kind": session["kind"],
                        "title_fr": session["title_fr"],
                        "title_en": session["title_en"],
                    },
                    "slot": passage.slot,
                    "starts_at": starts,
                    "ends_at": ends,
                    "duration_min": int((ends - starts).total_seconds() // 60),
                    "room": {
                        "name": room.get("name", ""),
                        "access_note": room.get("access_note", ""),
                        "is_accessible": room.get("is_accessible", False),
                    },
                    "title": passage.title,
                    "title_en": (slot or {}).get("title_en", "") if slot else "",
                    "reference": passage.reference,
                    "co_speakers": others,
                    "chairs": chairs,
                    "instructions": session.get("instructions", ""),
                }
            )
    entries.sort(key=lambda entry: (entry["starts_at"], entry["session"]["id"]))
    return entries


def agenda_calendar(user, *, now: dt.datetime) -> str:
    """Fichier ``.ics`` de « Mon passage » (I8) : un événement par passage, en UTC."""
    host = urlparse(settings.GESTCONF_PUBLIC_URL).hostname or "gest-conf"
    events = []
    for entry in my_agenda(user):
        code = entry["edition"]["code"]
        description = "\n".join(
            part
            for part in (
                entry["reference"],
                entry["session"]["title_fr"],
                ", ".join(entry["co_speakers"]),
                entry["instructions"],
            )
            if part
        )
        events.append(
            ical.Event(
                uid=f"{code}-{entry['session']['id']}-{entry['slot'] or 0}-{entry['role']}@{host}",
                starts_at=entry["starts_at"],
                ends_at=entry["ends_at"],
                summary=f"{code} · {entry['title']}",
                location=entry["room"]["name"],
                description=description,
            )
        )
    return ical.calendar(events, stamp=now, name="GEST-CONF")
