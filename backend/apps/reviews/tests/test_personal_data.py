"""Données personnelles des relecteurs (RG-18 ; plan L4 §3) : export, refus d'anonymiser
pendant une évaluation en cours, évaluation conservée sans nom."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import Profile
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.core.actor import Actor
from apps.core.errors import RuleViolation
from apps.reviews.models import (
    AssignmentStatus,
    Discussion,
    DiscussionMessage,
    Review,
    ReviewAssignment,
    ReviewerTrack,
    ReviewVersion,
)
from apps.reviews.personal_data import reviewer_duties
from apps.reviews.services import grids
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import complete_submission, user_actor

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


def reviewer_with_review():
    reviewer = VerifiedUserFactory(email="lea.martin@relecteurs.org")
    Profile.objects.update_or_create(
        user=reviewer, defaults={"first_name": "Léa", "last_name": "Martin"}
    )
    submission = complete_submission()
    workflow.transition(submission, S.SUBMITTED, user_actor(submission.submitter))
    submission.refresh_from_db()
    grid = grids.create_grid(submission.edition, name="Grille", actor=COMMAND)
    assignment = ReviewAssignment.objects.create(
        submission=submission, reviewer=reviewer, assigned_at=timezone.now(), active_key="k1"
    )
    review = Review.objects.create(
        assignment=assignment,
        grid=grid,
        comment_to_authors="Bon travail. Léa Martin",
        comment_to_committee="Signé : lea.martin@relecteurs.org",
    )
    ReviewVersion.objects.create(
        review=review, version=1, at=timezone.now(), snapshot={"comment": "Léa Martin"}
    )
    ReviewerTrack.objects.create(user=reviewer, edition=submission.edition, track=submission.track)
    discussion = Discussion.objects.create(submission=submission, opened_at=timezone.now())
    DiscussionMessage.objects.create(
        discussion=discussion, author=reviewer, body="Je suis Léa Martin", at=timezone.now()
    )
    return reviewer, submission, assignment, review


def test_reviewer_export_lists_assignments_reviews_messages_and_expertise():
    reviewer, submission, _assignment, _review = reviewer_with_review()
    data = export_user_data(reviewer, actor=COMMAND)
    assert data["review_assignments"][0]["reference"] == submission.reference
    assert data["reviews"][0]["comment_to_authors"].startswith("Bon travail")
    assert data["discussion_messages"][0]["body"] == "Je suis Léa Martin"
    assert data["review_expertise"][0]["track"] == submission.track.code


def test_rg18_anonymization_refused_while_review_in_progress_then_scrubbed():
    """RG-18 : refus tant qu'une évaluation est en cours ; ensuite, l'évaluation reste, sans
    nom (commentaires, messages et versions nettoyés), les expertises sont supprimées."""
    reviewer, submission, assignment, review = reviewer_with_review()
    Submission.objects.filter(pk=submission.pk).update(status=S.UNDER_REVIEW)
    assert reviewer_duties(reviewer) == [f"review:{submission.reference}"]
    with pytest.raises(RuleViolation):
        anonymize_user(reviewer, actor=COMMAND, reason="Demande")
    ReviewAssignment.objects.filter(pk=assignment.pk).update(
        status=AssignmentStatus.DECLINED, active_key=None
    )
    anonymize_user(reviewer, actor=COMMAND, reason="Demande")
    review.refresh_from_db()
    assert "Léa Martin" not in review.comment_to_authors
    assert "lea.martin@" not in review.comment_to_committee
    assert "Léa Martin" not in ReviewVersion.objects.get(review=review).snapshot["comment"]
    assert DiscussionMessage.objects.get().body == "Je suis Anonyme"
    assert not ReviewerTrack.objects.filter(user=reviewer).exists()
    assert Review.objects.filter(pk=review.pk).exists()
