"""Assistants des tests de l'évaluation (plan L4)."""

from __future__ import annotations

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import make_member
from apps.submissions.models import Submission, SubmissionAuthor, SubmissionStatus
from apps.submissions.tests.factories import author_user, complete_submission, open_edition


def in_status(submission: Submission, status: str) -> Submission:
    """Statut posé directement (test) : la clôture de l'appel n'est pas simulée ici."""
    reference = submission.reference or f"{submission.edition.code}-{submission.pk:04d}"
    Submission.objects.filter(pk=submission.pk).update(status=status, reference=reference)
    submission.refresh_from_db()
    return submission


def screening_submission(edition=None, *, institution: str = "Université de Cocody", **fields):
    """Soumission en recevabilité ; auteur « Kofi Mensah » (traceurs des tests d'identité)."""
    edition = edition or open_edition()
    submitter = author_user(first="Kofi", last="Mensah")
    submission = complete_submission(edition, submitter, **fields)
    SubmissionAuthor.objects.filter(submission=submission).update(institution=institution)
    return in_status(submission, SubmissionStatus.SCREENING)


def reviewer(edition, *, institution: str = "", role: str = Role.SC_MEMBER, **fields):
    user = make_member(edition, role, **fields)
    Profile.objects.update_or_create(
        user=user,
        defaults={
            "first_name": "Rita",
            "last_name": f"Relectrice{user.pk}",
            "institution": institution,
            "country": "CI",
        },
    )
    return user
