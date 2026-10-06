"""Assistants des tests du programme (plan L5)."""

from __future__ import annotations

import datetime as dt

from apps.conferences.tests.factories import SubmissionTypeFactory
from apps.core.actor import Actor
from apps.program.services import planning
from apps.reviews.tests.helpers import in_status
from apps.submissions.models import Submission, SubmissionAuthor
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import author_user, complete_submission, open_edition

COMMAND = Actor.command("cli:test")


def local(day: int, hour: int, minute: int = 0) -> dt.datetime:
    """Heure locale de l'édition de test (juin 2027, Africa/Abidjan = UTC)."""
    return dt.datetime(2027, 6, day, hour, minute)


def utc(day: int, hour: int, minute: int = 0) -> dt.datetime:
    return dt.datetime(2027, 6, day, hour, minute, tzinfo=dt.UTC)


def edition(**fields):
    """Édition publiée du 1er au 3 juin 2027 (fuseau d'Abidjan, sans heure d'été)."""
    return open_edition(**fields)


def confirmed(edition, *, first="Awa", last="Zadi", duration=None, **fields) -> Submission:
    """Communication confirmée (I5), de durée par défaut ``duration`` (type de communication)."""
    submission_type = SubmissionTypeFactory(
        edition=edition, file_policy="none", default_duration_min=duration
    )
    submission = complete_submission(
        edition, author_user(first=first, last=last), submission_type=submission_type, **fields
    )
    return in_status(submission, S.CONFIRMED)


def coauthor(submission: Submission, *, email: str, first="Mariam", last="Traoré", presenter=True):
    """Co-auteur sans compte, identifié par son adresse (RG-12)."""
    position = submission.authors.count() + 1
    return SubmissionAuthor.objects.create(
        submission=submission,
        position=position,
        first_name=first,
        last_name=last,
        email=email,
        is_presenter=presenter,
    )


def session(edition, start: dt.datetime, end: dt.datetime, *, room=None, title="Session"):
    return planning.create_session(
        edition,
        {
            "kind": "parallel",
            "title_fr": title,
            "starts_local": start,
            "ends_local": end,
            "room": room,
        },
        actor=COMMAND,
    )
