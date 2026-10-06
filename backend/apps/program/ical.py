"""iCalendar minimal (RFC 5545), écrit à la main sans dépendance (plan L5, bilan de L5.0).

Sous-ensemble utile : ``VCALENDAR`` et ``VEVENT``, heures en UTC, textes échappés, lignes de
75 octets au plus pliées sans couper un caractère UTF-8, fins de ligne CRLF.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass

PRODID = "-//GEST-CONF//Programme//FR"


@dataclass(frozen=True, slots=True)
class Event:
    uid: str
    starts_at: dt.datetime
    ends_at: dt.datetime
    summary: str
    location: str = ""
    description: str = ""


def escape(text: str) -> str:
    """Échappement des textes (RFC 5545 §3.3.11) : barre oblique inverse, point-virgule,
    virgule, sauts de ligne."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold(line: str) -> str:
    """Lignes de 75 octets au plus ; la suite commence par une espace (RFC 5545 §3.1)."""
    parts: list[str] = []
    current = b""
    for char in line:
        encoded = char.encode("utf-8")
        limit = 75 if not parts else 74
        if len(current) + len(encoded) > limit:
            parts.append(current.decode("utf-8"))
            current = b""
        current += encoded
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def utc(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%SZ")


def calendar(events: Iterable[Event], *, stamp: dt.datetime, name: str = "") -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    if name:
        lines.append(f"X-WR-CALNAME:{escape(name)}")
    for event in events:
        lines += [
            "BEGIN:VEVENT",
            f"UID:{event.uid}",
            f"DTSTAMP:{utc(stamp)}",
            f"DTSTART:{utc(event.starts_at)}",
            f"DTEND:{utc(event.ends_at)}",
            f"SUMMARY:{escape(event.summary)}",
        ]
        if event.location:
            lines.append(f"LOCATION:{escape(event.location)}")
        if event.description:
            lines.append(f"DESCRIPTION:{escape(event.description)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + "\r\n" for line in lines)
