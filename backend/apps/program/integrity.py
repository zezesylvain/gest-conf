"""Contrôles d'intégrité du programme (``check_integrity``, plan L5 §3)."""

from __future__ import annotations

import datetime as dt

from apps.program.models import Session, Slot
from apps.submissions.models import SubmissionStatus as S

PLACED = (S.CONFIRMED, S.SCHEDULED)


def check_slots() -> list[str]:
    """I3 : créneaux contigus, dans l'ordre, cohérents avec le début de leur session et le
    tampon de l'édition ; communications placées confirmées ou programmées (I5)."""
    problems = []
    sessions = Session.objects.select_related("edition").prefetch_related("slots")
    for session in sessions.iterator(chunk_size=200):
        buffer = dt.timedelta(minutes=session.edition.session_buffer_minutes)
        cursor = session.starts_at
        for index, slot in enumerate(sorted(session.slots.all(), key=lambda s: (s.position, s.pk))):
            if index:
                cursor += buffer
            expected = (index, cursor, cursor + dt.timedelta(minutes=slot.duration_min))
            if (slot.position, slot.starts_at, slot.ends_at) != expected:
                problems.append(f"créneau {slot.pk} : position ou horaire incohérents")
            cursor = expected[2]
    misplaced = Slot.objects.filter(submission__isnull=False).exclude(submission__status__in=PLACED)
    for pk in misplaced.values_list("pk", flat=True):
        problems.append(f"créneau {pk} : communication ni confirmée ni programmée")
    return problems


def check_publication() -> list[str]:
    """I6 : une communication « programmée » figure dans la dernière publication de son
    édition, et une communication publiée n'est pas restée « confirmée »."""
    from apps.program.models import ProgramPublication
    from apps.submissions.models import Submission

    problems = []
    latest: dict[int, set[int]] = {}
    for row in ProgramPublication.objects.order_by("edition_id", "version"):
        latest[row.edition_id] = {
            slot["submission"]["id"]
            for session in row.snapshot.get("sessions", [])
            for slot in session.get("slots", [])
            if slot.get("submission")
        }
    for pk, edition_id, status in Submission.objects.filter(
        status__in=(S.CONFIRMED, S.SCHEDULED)
    ).values_list("pk", "edition_id", "status"):
        published = pk in latest.get(edition_id, set())
        if status == S.SCHEDULED and not published:
            problems.append(f"soumission {pk} : programmée sans figurer au programme publié")
        if status == S.CONFIRMED and published:
            problems.append(f"soumission {pk} : publiée mais restée confirmée")
    return problems
