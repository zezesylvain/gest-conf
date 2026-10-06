"""Lot L4, étape L4.3 : évaluation (H4, H5), RG-05 (verrou), RG-06 (versions), RG-07
(REVIEWED automatique), RG-08 (discussion), divergence (H12), refus du relecteur (H8, H15),
suivi du président."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.reviews.models import (
    AssignmentStatus,
    ConflictKind,
    ConflictOfInterest,
    ConflictSource,
    Discussion,
    EvaluationGrid,
    Review,
    ReviewStatus,
    ReviewVersion,
)
from apps.reviews.services import assignments
from apps.reviews.services import reviews as services
from apps.reviews.services.grids import create_grid
from apps.reviews.tests.helpers import in_status, reviewer, screening_submission
from apps.submissions.models import StatusHistory
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import user_actor

pytestmark = pytest.mark.django_db

SCORES = {"originalite": "4", "methode": "4", "pertinence": "3", "redaction": "3", "impact": "3"}
FULL = {
    "scores": SCORES,
    "recommendation": "accept",
    "confidence": 4,
    "comment_to_authors": "Solide.",
}


@pytest.fixture
def review_world():
    """Soumission en évaluation, deux relecteurs requis et affectés, grille par défaut."""
    submission = screening_submission()
    edition = submission.edition
    edition.reviewers_per_submission = 2
    edition.save()
    chair = make_member(edition, Role.SC_CHAIR)
    actor = user_actor(chair)
    grid = create_grid(edition, name="Grille", actor=actor)
    first, second = reviewer(edition), reviewer(edition)
    a1 = assignments.assign(submission, first, actor=actor)
    a2 = assignments.assign(submission, second, actor=actor)
    assignments.screen(submission, admissible=True, reason="", actor=actor)
    return {
        "submission": submission,
        "edition": edition,
        "chair": chair,
        "actor": actor,
        "grid": grid,
        "reviewers": (first, second),
        "assignments": (a1, a2),
    }


def submit(world, index: int, data=FULL):
    user = world["reviewers"][index]
    return services.submit_review(world["assignments"][index], data, actor=user_actor(user))


# --- Brouillon et calcul (H4, H5, RG-05) -----------------------------------------------------


def test_h4_draft_score_is_computed_by_the_server_and_locks_the_grid(review_world):
    """H4 et RG-05 : note pondérée calculée par le serveur ; grille verrouillée au premier
    enregistrement."""
    user = review_world["reviewers"][0]
    review = services.save_review(
        review_world["assignments"][0],
        {"scores": SCORES, "weighted_score": "99"},
        actor=user_actor(user),
    )
    # (4*25 + 4*30 + 3*15 + 3*15 + 3*15) / 100 = 3,55 sur 5 → 71,00 sur 100.
    assert review.weighted_score == Decimal("71.00")
    assert review.status == ReviewStatus.DRAFT
    assert EvaluationGrid.objects.get(pk=review_world["grid"].pk).locked_at is not None
    partial = services.save_review(
        review_world["assignments"][0], {"scores": {"originalite": "5"}}, actor=user_actor(user)
    )
    assert partial.weighted_score is None  # critères obligatoires manquants
    assert partial.scores.count() == 1


def test_h5_validation_of_scores_and_fields(review_world):
    user = review_world["reviewers"][0]
    assignment = review_world["assignments"][0]
    for bad in (
        {"scores": {"inconnu": "3"}},
        {"scores": {"originalite": "6"}},
        {"scores": {"originalite": "2.25"}},
        {"confidence": 9},
        {"recommendation": "peut-être"},
        {"suggested_type": "inexistant"},
    ):
        with pytest.raises(Invalid):
            services.save_review(assignment, bad, actor=user_actor(user))
    with pytest.raises(Invalid) as error:
        services.submit_review(assignment, {"scores": SCORES}, actor=user_actor(user))
    assert set(error.value.fields) == {"recommendation", "confidence", "comment_to_authors"}


def test_rg03_only_the_assigned_reviewer_writes(review_world):
    other = reviewer(review_world["edition"])
    with pytest.raises(RuleViolation) as error:
        services.save_review(review_world["assignments"][0], FULL, actor=user_actor(other))
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN


# --- RG-06 et RG-07 ---------------------------------------------------------------------------


def test_rg06_each_submission_is_a_version_and_a_submitted_review_is_resubmitted(review_world):
    review = submit(review_world, 0)
    assert (review.status, review.version) == (ReviewStatus.SUBMITTED, 1)
    with pytest.raises(RuleViolation) as error:
        services.save_review(
            review_world["assignments"][0], FULL, actor=user_actor(review_world["reviewers"][0])
        )
    assert error.value.code == ErrorCode.INVALID_TRANSITION
    changed = submit(review_world, 0, {**FULL, "scores": {**SCORES, "impact": "5"}})
    assert changed.version == 2
    versions = list(ReviewVersion.objects.filter(review=review).order_by("version"))
    assert [v.snapshot["scores"]["impact"] for v in versions] == ["3.0", "5.0"]
    assert versions[1].snapshot["weighted_score"] == "77.00"
    assert AuditLog.objects.filter(action="review.resubmitted").count() == 1


def test_rg07_reviewed_when_the_required_reviews_are_submitted(review_world):
    submission = review_world["submission"]
    submit(review_world, 0)
    submission.refresh_from_db()
    assert submission.status == S.UNDER_REVIEW
    submit(review_world, 1)
    submission.refresh_from_db()
    assert submission.status == S.REVIEWED
    history = StatusHistory.objects.get(to_status=S.REVIEWED)
    assert history.actor_label == "review:rg07"
    # H14 : un relecteur supplémentaire ne fait pas revenir en arrière.
    extra = assignments.assign(
        submission, reviewer(review_world["edition"]), actor=review_world["actor"]
    )
    submission.refresh_from_db()
    assert submission.status == S.REVIEWED
    assert extra.status == AssignmentStatus.ACTIVE


def test_rg07_guard_refuses_reviewed_without_the_required_reviews(review_world):
    from apps.submissions import workflow

    with pytest.raises(RuleViolation):
        workflow.transition(review_world["submission"], S.REVIEWED, Actor.system("job:test"))


def test_h13_no_edit_once_the_assignment_ended(review_world):
    assignment = review_world["assignments"][0]
    assignments.cancel_assignment(assignment, reason="Remplacé", actor=review_world["actor"])
    with pytest.raises(RuleViolation) as error:
        services.save_review(assignment, FULL, actor=user_actor(review_world["reviewers"][0]))
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN


# --- RG-08 : discussion -----------------------------------------------------------------------


def test_rg08_discussion_opens_when_all_reviews_are_in(review_world):
    submission = review_world["submission"]
    a1 = review_world["assignments"][0]
    submit(review_world, 0)
    assert not Discussion.objects.exists()
    assert not services.can_see_discussion(a1)
    submit(review_world, 1)
    discussion = Discussion.objects.get(submission=submission)
    assert discussion.opened_by is None
    a1.refresh_from_db()
    assert services.can_see_discussion(a1)
    assert AuditLog.objects.filter(action="review.discussion_opened").count() == 1


def test_rg08_reviewer_sees_others_only_after_submitting(review_world):
    """RG-08 : discussion ouverte par le président ; le relecteur qui n'a pas envoyé son
    évaluation n'y a pas accès."""
    submission = review_world["submission"]
    submit(review_world, 0)
    services.open_discussion_by_chair(submission, actor=review_world["actor"])
    a1, a2 = review_world["assignments"]
    first, second = review_world["reviewers"]
    url = f"/v1/manage/editions/{review_world['edition'].pk}/reviews/assignments"
    response = client_for(second).get(f"{url}/{a2.pk}/discussion")
    assert (response.status_code, response.json()["code"]) == (409, "discussion_closed")
    response = client_for(second).post(f"{url}/{a2.pk}/discussion", {"body": "x"}, format="json")
    assert response.status_code == 409
    payload = client_for(first).get(f"{url}/{a1.pk}/discussion").json()
    assert [r["mine"] for r in payload["reviews"]] == [True]


def test_rg08_messages_and_closing_after_decision(review_world):
    submission = review_world["submission"]
    submit(review_world, 0)
    submit(review_world, 1)
    a1 = review_world["assignments"][0]
    first = review_world["reviewers"][0]
    with pytest.raises(Invalid):
        services.post_message(submission, " ", actor=user_actor(first), assignment=a1)
    services.post_message(submission, "Bonne note.", actor=user_actor(first), assignment=a1)
    services.post_message(submission, "Merci.", actor=review_world["actor"])
    in_status(submission, S.ACCEPTED)
    with pytest.raises(RuleViolation) as error:
        services.post_message(submission, "Trop tard", actor=review_world["actor"])
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN
    # Après la décision, le relecteur relit son évaluation et la discussion.
    url = f"/v1/manage/editions/{review_world['edition'].pk}/reviews/assignments/{a1.pk}"
    client = client_for(first)
    assert client.get(url).json()["can_edit"] is False
    assert len(client.get(f"{url}/discussion").json()["messages"]) == 2


# --- Divergence (H12) -------------------------------------------------------------------------


def test_h12_divergence_is_reported_once_to_the_sc_chair(review_world):
    low = {**FULL, "scores": dict.fromkeys(SCORES, "1")}  # 20,00
    high = {**FULL, "scores": dict.fromkeys(SCORES, "5")}  # 100,00
    submit(review_world, 0, low)
    submit(review_world, 1, high)
    state = services.summary(review_world["submission"])
    assert (state.spread, state.divergent, state.final) == (
        Decimal("80.00"),
        True,
        Decimal("60.00"),
    )
    (mail,) = OutboxEmail.objects.filter(template_code="review/email/divergence")
    assert mail.to_email == review_world["chair"].email
    assert "80.00" in mail.body_text
    submit(review_world, 1, {**high, "comment_to_authors": "Modifié"})
    assert OutboxEmail.objects.filter(template_code="review/email/divergence").count() == 1


def test_h4_final_score_weighted_by_confidence_when_enabled(review_world):
    edition = review_world["edition"]
    edition.confidence_weighted_score = True
    edition.save()
    submit(review_world, 0, {**FULL, "scores": dict.fromkeys(SCORES, "1"), "confidence": 1})
    submit(review_world, 1, {**FULL, "scores": dict.fromkeys(SCORES, "5"), "confidence": 3})
    # (20*1 + 100*3) / 4 = 80.
    assert services.summary(review_world["submission"]).final == Decimal("80.00")


# --- Refus du relecteur (H8, H15) ------------------------------------------------------------


def test_h15_decline_with_conflict_informs_the_sc_chair(review_world):
    a1 = review_world["assignments"][0]
    first = review_world["reviewers"][0]
    services.decline(
        a1, reason="Ancien doctorant de l'auteur", conflict=True, actor=user_actor(first)
    )
    a1.refresh_from_db()
    assert (a1.status, a1.active_key) == (AssignmentStatus.DECLINED, None)
    conflict = ConflictOfInterest.objects.get()
    assert (conflict.kind, conflict.source, conflict.declared_by) == (
        ConflictKind.DECLARED,
        ConflictSource.REVIEWER,
        first,
    )
    (mail,) = OutboxEmail.objects.filter(template_code="review/email/declined")
    assert mail.to_email == review_world["chair"].email
    assert "Relectrice" not in mail.body_text  # nom du relecteur omis
    assert AuditLog.objects.filter(action="review.assignment_declined").count() == 1
    with pytest.raises(RuleViolation):
        assignments.assign(review_world["submission"], first, actor=review_world["actor"])


def test_h15_decline_refusals(review_world):
    a1 = review_world["assignments"][0]
    first = review_world["reviewers"][0]
    with pytest.raises(Invalid):
        services.decline(a1, reason="", conflict=False, actor=user_actor(first))
    submit(review_world, 0)
    with pytest.raises(RuleViolation) as error:
        services.decline(a1, reason="Plus le temps", conflict=False, actor=user_actor(first))
    assert error.value.code == ErrorCode.INVALID_TRANSITION


# --- API du président ------------------------------------------------------------------------


def test_president_reviews_endpoint_shows_names_and_discussion(review_world):
    submit(review_world, 0)
    submit(review_world, 1)
    edition = review_world["edition"]
    submission = review_world["submission"]
    client = client_for(review_world["chair"])
    base = f"/v1/manage/editions/{edition.pk}/review-submissions/{submission.pk}"
    response = client.post(f"{base}/discussion/messages", {"body": "Avis ?"}, format="json")
    assert response.status_code == 201
    payload = client.get(f"{base}/reviews").json()
    names = {review["reviewer"]["name"] for review in payload["reviews"]}
    assert names == {f"Rita Relectrice{u.pk}" for u in review_world["reviewers"]}
    assert payload["final_score"] == "71.00" and payload["divergent"] is False
    assert payload["messages"][0]["author"]["id"] == review_world["chair"].pk
    assert payload["messages"][0]["pseudonym_rank"] is None


def test_president_opens_the_discussion_and_reads_progress(review_world):
    edition = review_world["edition"]
    submission = review_world["submission"]
    client = client_for(review_world["chair"])
    base = f"/v1/manage/editions/{edition.pk}"
    response = client.post(f"{base}/review-submissions/{submission.pk}/discussion/open")
    assert response.status_code == 200
    assert response.json()["discussion_opened_at"] is not None
    submit(review_world, 0, {**FULL, "scores": dict.fromkeys(SCORES, "1")})
    submit(review_world, 1, {**FULL, "scores": dict.fromkeys(SCORES, "5")})
    progress = client.get(f"{base}/review-progress").json()
    assert progress["threshold"] == "30.00"
    rows = {row["id"]: row for row in progress["reviewers"]}
    first = review_world["reviewers"][0]
    assert (rows[first.pk]["active"], rows[first.pk]["submitted"], rows[first.pk]["late"]) == (
        1,
        1,
        0,
    )
    assert progress["tracks"] == [{"code": submission.track.code, "in_review": 1, "reviewed": 1}]
    assert progress["divergent"] == [
        {
            "id": submission.pk,
            "reference": submission.reference,
            "title": submission.title,
            "spread": "80.00",
        }
    ]


def test_no_grid_means_review_not_open():
    submission = in_status(screening_submission(), S.UNDER_REVIEW)
    edition = submission.edition
    actor = user_actor(make_member(edition, Role.SC_CHAIR))
    user = reviewer(edition)
    assignment = assignments.assign(submission, user, actor=actor)
    with pytest.raises(RuleViolation) as error:
        services.save_review(assignment, FULL, actor=user_actor(user))
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN
    assert not Review.objects.exists()
