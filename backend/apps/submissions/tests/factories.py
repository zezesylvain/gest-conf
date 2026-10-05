"""Fabriques et assistants des tests de soumission."""

from __future__ import annotations

import datetime as dt

from django.utils import timezone

from apps.accounts.models import Profile
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.models import EditionStatus, KeyDateCode
from apps.conferences.tests.factories import (
    EditionFactory,
    KeyDateFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from apps.core.actor import Actor, ActorKind
from apps.submissions.declarations import DECLARATIONS
from apps.submissions.models import Submission, SubmissionAuthor

ACCEPTED_DECLARATIONS = {
    code: {"accepted": True, "text_version": version} for code, version in DECLARATIONS.items()
}


def open_edition(*, opens_in_days: int = -10, closes_in_days: int = 10, **fields):
    """Édition publiée, appel ouvert (par défaut) autour de maintenant."""
    edition = EditionFactory(status=EditionStatus.PUBLISHED, **fields)
    now = timezone.now()
    KeyDateFactory(
        edition=edition, code=KeyDateCode.CALL_OPEN, at=now + dt.timedelta(opens_in_days)
    )
    KeyDateFactory(
        edition=edition, code=KeyDateCode.CALL_CLOSE, at=now + dt.timedelta(closes_in_days)
    )
    return edition


def user_actor(user) -> Actor:
    return Actor(kind=ActorKind.USER, user=user)


def author_user(first="Awa", last="Zadi", **fields):
    user = VerifiedUserFactory(**fields)
    Profile.objects.update_or_create(
        user=user,
        defaults={"first_name": first, "last_name": last, "institution": "Univ.", "country": "CI"},
    )
    return user


def complete_submission(edition=None, submitter=None, **fields) -> Submission:
    """Brouillon complet (RG-01 satisfaite), prêt à être soumis."""
    edition = edition or open_edition()
    submitter = submitter or author_user()
    values = {
        "title": "Une étude",
        "abstract": "Un résumé de quelques mots.",
        "keywords": ["ia"],
        "language": "fr",
        "track": TrackFactory(edition=edition),
        "submission_type": SubmissionTypeFactory(edition=edition, file_policy="none"),
        "declarations": dict(ACCEPTED_DECLARATIONS),
    }
    values.update(fields)
    submission = Submission.objects.create(edition=edition, submitter=submitter, **values)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=1,
        user=submitter,
        first_name=submitter.profile.first_name,
        last_name=submitter.profile.last_name,
        email=submitter.email,
        is_corresponding=True,
        is_presenter=True,
    )
    return submission
