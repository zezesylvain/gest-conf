"""Segments des envois groupés : auteurs (plan L8, N11).

Un auteur est le compte qui a soumis, ou un co-auteur rattaché à un compte. « Acceptés » ne
lit que des statuts posés à la **publication** des décisions (RG-09) : une décision
provisoire n'y fait entrer personne.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

ACCEPTED = (
    S.ACCEPTED,
    S.ACCEPTED_MINOR,
    S.CAMERA_READY_RECEIVED,
    S.CONFIRMED,
    S.SCHEDULED,
    S.PRESENTED,
    S.PUBLISHED,
)


def _authors(edition, submissions):
    return User.objects.filter(
        Q(pk__in=submissions.values("submitter_id"))
        | Q(pk__in=submissions.filter(authors__user__isnull=False).values("authors__user_id"))
    )


def submitted_authors(edition):
    rows = Submission.objects.filter(edition=edition).exclude(status__in=(S.DRAFT, S.WITHDRAWN))
    return _authors(edition, rows)


def accepted_authors(edition):
    return _authors(edition, Submission.objects.filter(edition=edition, status__in=ACCEPTED))


def register_submissions_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(
        Segment("authors.submitted", _("Auteurs (soumission envoyée)"), submitted_authors, 10)
    )
    register_segment(Segment("authors.accepted", _("Auteurs acceptés"), accepted_authors, 11))
