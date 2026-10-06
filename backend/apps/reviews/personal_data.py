"""Données personnelles de l'évaluation (registre ``apps.core.personal_data``, RG-18 ;
plan L4 §3). Le relecteur est une personne : ses affectations, évaluations, messages,
conflits et expertises le concernent.

- **Export** : expertises, affectations, évaluations (notes et commentaires), messages de
  discussion, conflits le concernant ; comme auteur, lettres de réponse des versions finales.
- **Anonymisation** : refusée tant qu'une affectation active porte sur une soumission en cours
  d'évaluation d'une édition non archivée (``reviewer_duties``, comme F16). Sinon : expertises
  supprimées ; évaluations conservées **sans nom** (le compte est anonymisé), son nom et ses
  adresses retirés des commentaires, messages, motifs et clichés de version.
"""

from __future__ import annotations

from typing import Any

from apps.conferences.models import EditionStatus
from apps.core.personal_data import (
    AnonymizationContext,
    exempt_model,
    register_duty_check,
    register_personal_data,
)
from apps.reviews.models import (
    AssignmentStatus,
    ConflictOfInterest,
    DiscussionMessage,
    FinalVersion,
    Review,
    ReviewAssignment,
    ReviewerTrack,
    ReviewVersion,
)
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.personal_data import _scrubber

# Statuts où une évaluation est encore attendue ou discutée.
REVIEW_IN_PROGRESS = (S.SCREENING, S.UNDER_REVIEW, S.REVIEWED)


def reviewer_duties(user) -> list[str]:
    references = (
        ReviewAssignment.objects.filter(
            reviewer=user,
            status=AssignmentStatus.ACTIVE,
            submission__status__in=REVIEW_IN_PROGRESS,
        )
        .exclude(submission__edition__status=EditionStatus.ARCHIVED)
        .values_list("submission__reference", flat=True)
        .distinct()
    )
    return sorted(f"review:{reference}" for reference in references)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    assignments = (
        ReviewAssignment.objects.filter(reviewer=user)
        .select_related("submission")
        .order_by("assigned_at", "id")
    )
    reviews = (
        Review.objects.filter(assignment__reviewer=user)
        .select_related("assignment__submission")
        .prefetch_related("scores__criterion")
        .order_by("id")
    )
    return {
        "review_expertise": [
            {"edition": row.edition.code, "track": row.track.code}
            for row in ReviewerTrack.objects.filter(user=user).select_related("edition", "track")
        ],
        "review_assignments": [
            {
                "reference": row.submission.reference,
                "status": row.status,
                "assigned_at": _iso(row.assigned_at),
                "due_at": _iso(row.due_at),
                "reason": row.reason,
            }
            for row in assignments
        ],
        "reviews": [
            {
                "reference": review.assignment.submission.reference,
                "status": review.status,
                "recommendation": review.recommendation,
                "confidence": review.confidence,
                "weighted_score": str(review.weighted_score)
                if review.weighted_score is not None
                else None,
                "comment_to_authors": review.comment_to_authors,
                "comment_to_committee": review.comment_to_committee,
                "scores": {score.criterion.code: str(score.value) for score in review.scores.all()},
                "submitted_at": _iso(review.submitted_at),
            }
            for review in reviews
        ],
        "discussion_messages": [
            {"reference": row.discussion.submission.reference, "body": row.body, "at": _iso(row.at)}
            for row in DiscussionMessage.objects.filter(author=user)
            .select_related("discussion__submission")
            .order_by("at", "id")
        ],
        "conflicts_of_interest": [
            {"reference": row.submission.reference, "kind": row.kind, "source": row.source}
            for row in ConflictOfInterest.objects.filter(reviewer=user).select_related("submission")
        ],
        # En tant qu'auteur : lettres de réponse aux relecteurs de ses versions finales (H18).
        "final_versions": [
            {
                "reference": row.submission.reference,
                "response_letter": row.response_letter,
                "submitted_at": _iso(row.submitted_at),
            }
            for row in FinalVersion.objects.filter(submission__submitter=user).select_related(
                "submission"
            )
        ],
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    scrub = _scrubber(context)
    ReviewerTrack.objects.filter(user=user).delete()
    for review in Review.objects.filter(assignment__reviewer=user):
        fields = []
        for name in ("comment_to_authors", "comment_to_committee"):
            cleaned = scrub(getattr(review, name))
            if cleaned != getattr(review, name):
                setattr(review, name, cleaned)
                fields.append(name)
        if fields:
            review.save(update_fields=[*fields, "updated_at"])
    review_ids = list(Review.objects.filter(assignment__reviewer=user).values_list("id", flat=True))
    ReviewVersion.redact(review_ids, scrub)
    for message in DiscussionMessage.objects.filter(author=user):
        cleaned = scrub(message.body)
        if cleaned != message.body:
            message.body = cleaned
            message.save(update_fields=["body"])
    for final in FinalVersion.objects.filter(submission__submitter=user):
        cleaned = scrub(final.response_letter)
        if cleaned != final.response_letter:
            final.response_letter = cleaned
            final.save(update_fields=["response_letter", "updated_at"])
    for model, fields in (
        (ReviewAssignment, ("reason", "conflict_override_reason")),
        (ConflictOfInterest, ("reason", "overridden_reason")),
    ):
        for row in model.objects.filter(reviewer=user):
            changed = []
            for name in fields:
                cleaned = scrub(getattr(row, name))
                if cleaned != getattr(row, name):
                    setattr(row, name, cleaned)
                    changed.append(name)
            if changed:
                row.save(update_fields=changed)


def register_reviews_personal_data() -> None:
    register_personal_data(
        "reviews.reviews",
        models=(
            "reviews.ReviewerTrack",
            "reviews.ReviewAssignment",
            "reviews.ConflictOfInterest",
            "reviews.DiscussionMessage",
        ),
        export=_export,
        anonymize=_anonymize,
        rank=450,
    )
    register_duty_check(reviewer_duties)
    exempt_model(
        "reviews.Discussion",
        "opened_by : membre du comité qui ouvre la discussion (trace, sans texte libre).",
    )
    exempt_model(
        "reviews.Decision",
        "decided_by : président qui décide (trace de gestion) ; le texte de la décision "
        "concerne la soumission, pas la personne qui décide.",
    )
