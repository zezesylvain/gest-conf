"""Émargement des sessions et communications présentées (plan L7, K7, K8).

Tout se lit dans le **programme publié** (dernier instantané, plan L5, I6), jamais dans le
brouillon : seules ses sessions s'émargent, et le président de séance est celui qu'il
désigne. Le président de séance (``SESSION_CHAIR``) émarge ses sessions et marque leurs
communications présentées, sans autre droit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Count
from django.http import Http404
from django.utils.translation import gettext_lazy as _

from apps.core.errors import ErrorCode, RuleViolation
from apps.events.models import Checkin
from apps.program.models import Session
from apps.program.services.publication import latest_publication
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.conferences.models import Edition
    from apps.core.actor import Actor


def published_sessions(edition: Edition) -> list[dict[str, Any]]:
    """Sessions du programme publié dont la ligne existe encore (une session supprimée du
    brouillon après publication ne s'émarge plus)."""
    publication = latest_publication(edition)
    if publication is None:
        return []
    existing = set(Session.objects.filter(edition=edition).values_list("pk", flat=True))
    return [item for item in publication.snapshot["sessions"] if item["id"] in existing]


def published_session_ids(edition: Edition) -> set[int]:
    return {item["id"] for item in published_sessions(edition)}


def published_session(edition: Edition, session_id: int) -> dict[str, Any]:
    for item in published_sessions(edition):
        if item["id"] == session_id:
            return item
    raise Http404


def chairs_session(session: dict[str, Any], user: User | None) -> bool:
    """Président de séance de la session, d'après le programme publié."""
    if user is None:
        return False
    key = f"user:{user.pk}"
    return any(role["role"] == "chair" and role["key"] == key for role in session["roles"])


def chaired_session_ids(edition: Edition, user: User | None) -> set[int]:
    return {item["id"] for item in published_sessions(edition) if chairs_session(item, user)}


def attendance_counts(edition: Edition) -> dict[int, int]:
    rows = (
        Checkin.objects.filter(edition=edition, session__isnull=False, active_key__isnull=False)
        .values("session_id")
        .annotate(count=Count("pk"))
    )
    return {row["session_id"]: row["count"] for row in rows}


def day_sessions(edition: Edition, *, only: set[int] | None = None) -> list[dict[str, Any]]:
    """Sessions publiées pour l'écran du jour J : horaires, salle, créneaux avec le statut
    **courant** de chaque communication (présentée ou non), nombre de présents."""
    sessions = published_sessions(edition)
    if only is not None:
        sessions = [item for item in sessions if item["id"] in only]
    submission_ids = [
        slot["submission"]["id"]
        for item in sessions
        for slot in item["slots"]
        if slot.get("submission")
    ]
    statuses = dict(Submission.objects.filter(pk__in=submission_ids).values_list("pk", "status"))
    counts = attendance_counts(edition)
    result = []
    for item in sorted(sessions, key=lambda row: (row["starts_at"], row["id"])):
        slots = []
        for slot in item["slots"]:
            submission = slot.get("submission")
            slots.append(
                {
                    "id": slot["id"],
                    "starts_at": slot["starts_at"],
                    "ends_at": slot["ends_at"],
                    "title": submission["title"] if submission else slot["title_fr"],
                    "reference": submission["reference"] if submission else "",
                    "submission_id": submission["id"] if submission else None,
                    "presenters": [
                        author["name"] for author in submission["authors"] if author["presenter"]
                    ]
                    if submission
                    else [],
                    "status": statuses.get(submission["id"], "") if submission else "",
                }
            )
        result.append(
            {
                "id": item["id"],
                "title_fr": item["title_fr"],
                "title_en": item["title_en"] or item["title_fr"],
                "starts_at": item["starts_at"],
                "ends_at": item["ends_at"],
                "room": item["room"]["name"] if item["room"] else "",
                "chairs": [role["name"] for role in item["roles"] if role["role"] == "chair"],
                "attendance": counts.get(item["id"], 0),
                "slots": slots,
            }
        )
    return result


def session_guard(session: Session) -> None:
    """Garde de ``program`` : une session qui a des présences ne se supprime plus."""
    if Checkin.objects.filter(session=session).exists():
        raise RuleViolation(
            _("Des présences sont enregistrées pour cette session : elle ne se supprime plus."),
            code=ErrorCode.IN_USE,
        )


# --- Communications présentées (K8) ------------------------------------------------------------


def _slot(edition: Edition, session_id: int, slot_id: int) -> Submission:
    session = published_session(edition, session_id)
    for slot in session["slots"]:
        if slot["id"] == slot_id and slot.get("submission"):
            submission = Submission.objects.filter(
                edition=edition, pk=slot["submission"]["id"]
            ).first()
            if submission is not None:
                return submission
    raise Http404


def mark_presented(edition: Edition, session_id: int, slot_id: int, *, actor: Actor) -> Submission:
    """``SCHEDULED → PRESENTED`` par le workflow, qui vérifie les droits (``program.write`` ou
    délégation au président de la séance, ``chair_grant``)."""
    submission = _slot(edition, session_id, slot_id)
    return workflow.transition(submission, S.PRESENTED, actor)


def unmark_presented(
    edition: Edition, session_id: int, slot_id: int, *, reason: str, actor: Actor
) -> Submission:
    """Correction (``PRESENTED → SCHEDULED``) : ``program.write`` seulement, motif obligatoire."""
    submission = _slot(edition, session_id, slot_id)
    return workflow.transition(submission, S.SCHEDULED, actor, reason=reason)


def chair_grant(submission: Submission, actor: Actor) -> bool:
    """Délégation au workflow (``SCHEDULED → PRESENTED``) : l'acteur préside, au programme
    publié, la session où la communication est placée."""
    for item in published_sessions(submission.edition):
        placed = any(
            (slot.get("submission") or {}).get("id") == submission.pk for slot in item["slots"]
        )
        if placed:
            return chairs_session(item, actor.user)
    return False
