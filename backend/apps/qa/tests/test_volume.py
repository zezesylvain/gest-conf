"""Données de volume du test de charge (plan L9, S6)."""

from __future__ import annotations

import io

import pytest
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.qa.fictitious import FICTITIOUS_CONFERENCE, FICTITIOUS_DOMAIN
from apps.registrations.models import Registration, RegistrationStatus
from apps.reviews.models import Review, ReviewAssignment
from apps.submissions.models import Submission, SubmissionStatus

pytestmark = pytest.mark.django_db

SMALL = ["--submissions", "4", "--reviewers", "3", "--participants", "6", "--drafts", "2"]


def seed(*extra: str) -> str:
    output = io.StringIO()
    call_command("seed_volume", "--confirm-fictitious", *SMALL, *extra, stdout=output)
    return output.getvalue()


def test_s6_seed_volume_goes_through_the_workflows():
    """Statuts écrits par les workflows : soumissions en évaluation, brouillons, inscriptions
    confirmées par un virement enregistré ou en attente ; comptes fictifs seulement."""
    output = seed()
    evaluation = Submission.objects.filter(edition__code="FICTIFEVAL")
    assert evaluation.count() == 4
    assert set(evaluation.values_list("status", flat=True)) <= {
        SubmissionStatus.UNDER_REVIEW,
        SubmissionStatus.REVIEWED,
    }
    assert all(reference for reference in evaluation.values_list("reference", flat=True))
    assert ReviewAssignment.objects.filter(submission__in=evaluation).count() == 8
    assert Review.objects.filter(submitted_at__isnull=False).count() > 0
    drafts = Submission.objects.filter(edition__code="FICTIFAPPEL")
    assert set(drafts.values_list("status", flat=True)) == {SubmissionStatus.DRAFT}
    registrations = Registration.objects.filter(edition__code="FICTIFAPPEL")
    assert registrations.count() == 6
    assert registrations.filter(status=RegistrationStatus.CONFIRMED).count() == 4
    assert registrations.filter(status=RegistrationStatus.PENDING).count() == 2
    assert not User.objects.exclude(email__endswith="@" + FICTITIOUS_DOMAIN).exists()
    # Mot de passe et secret affichés une fois, tirés au hasard.
    assert "mot de passe des comptes fictifs" in output and "secret TOTP" in output


def test_s6_fictitious_emails_are_never_sent():
    """Domaine réservé .invalid : la file annule chaque e-mail, rien ne part."""
    seed()
    queued = OutboxEmail.objects.filter(to_email__endswith="@" + FICTITIOUS_DOMAIN)
    assert queued.exists()
    call_command("run_jobs", verbosity=0)
    assert not queued.exclude(status=OutboxStatus.CANCELLED).exists()
    assert mail.outbox == []


def test_s6_seed_volume_requires_confirmation_and_refuses_real_data():
    with pytest.raises(CommandError, match="confirm-fictitious"):
        call_command("seed_volume", *SMALL)
    from apps.accounts.tests.factories import VerifiedUserFactory

    VerifiedUserFactory(email="personne@exemple.org")
    with pytest.raises(CommandError, match="données réelles \\(1 comptes\\)"):
        seed()
    from apps.submissions.tests.factories import complete_submission

    complete_submission()
    with pytest.raises(CommandError, match="soumissions"):
        seed()


def test_s6_seed_volume_runs_once_and_is_audited():
    seed()
    from apps.core.models import AuditLog

    (entry,) = AuditLog.objects.filter(action="qa.volume_seeded")
    assert entry.after["counts"]["submissions"] == 4
    from apps.conferences.models import Conference

    assert Conference.objects.filter(slug=FICTITIOUS_CONFERENCE).exists()
    with pytest.raises(CommandError, match="existent déjà"):
        seed()
