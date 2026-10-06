"""Évaluations, discussion et divergence (plan L4, H4, H5, H12, H13 ; RG-06, RG-07, RG-08).

- **Brouillon** (``save_review``) : copie de travail ; la note pondérée est recalculée par le
  serveur à chaque enregistrement (H4), la grille est verrouillée au premier (RG-05).
- **Envoi** (``submit_review``) : contrôle de complétude, version en ajout seul (RG-06) ; une
  évaluation envoyée se modifie par un nouvel envoi, jusqu'à la décision (H13).
- **RG-07** : au dernier envoi requis, la soumission passe en ``REVIEWED`` (système).
- **RG-08** : la discussion s'ouvre d'elle-même quand toutes les évaluations actives sont
  envoyées, ou à la main par le président ; un relecteur n'y voit les autres évaluations
  qu'après avoir envoyé la sienne.
- **Divergence** (H12) : écart maximal entre notes au-delà du seuil de l'édition → signalée
  (suivi) et e-mail unique au président du CS ; aucune action automatique.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.invitations import display_name
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, SubmissionType
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.reviews.models import (
    AssignmentStatus,
    ConflictKind,
    ConflictOfInterest,
    ConflictSource,
    Discussion,
    DiscussionMessage,
    EvaluationGrid,
    Recommendation,
    Review,
    ReviewAssignment,
    ReviewScore,
    ReviewStatus,
    ReviewVersion,
)
from apps.reviews.services.assignments import (
    REVIEWABLE,
    end_assignment,
    lock_submission,
    reviewable_assignments,
    reviewers_of,
    submitted_count,
)
from apps.reviews.services.grids import grid_for, lock_grid
from apps.reviews.services.scoring import CriterionWeight, divergence, final_score, weighted_score
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

COMMENT_MAX = 20_000
MESSAGE_MAX = 5_000
REVIEW_FIELDS = (
    "recommendation",
    "confidence",
    "comment_to_authors",
    "comment_to_committee",
    "ethics_flag",
    "plagiarism_flag",
)


# --- Lecture ------------------------------------------------------------------------------


def grid_of(assignment: ReviewAssignment) -> EvaluationGrid | None:
    """Grille de l'évaluation : celle de l'évaluation commencée, sinon la grille applicable."""
    review = getattr(assignment, "review", None)
    if review is not None:
        return review.grid
    submission = assignment.submission
    return grid_for(submission.edition, submission.submission_type)


def scores_of(review: Review) -> dict[str, Decimal]:
    return {score.criterion.code: score.value for score in review.scores.all()}


def can_edit(assignment: ReviewAssignment) -> bool:
    """Évaluation modifiable : affectation active, soumission en évaluation (H13)."""
    return (
        assignment.status == AssignmentStatus.ACTIVE and assignment.submission.status in REVIEWABLE
    )


def can_see_discussion(assignment: ReviewAssignment) -> bool:
    """RG-08 : discussion ouverte et évaluation du relecteur envoyée."""
    review = getattr(assignment, "review", None)
    return (
        Discussion.objects.filter(submission_id=assignment.submission_id).exists()
        and review is not None
        and review.status == ReviewStatus.SUBMITTED
    )


@dataclass(frozen=True, slots=True)
class Summary:
    """Notes d'une soumission : évaluations envoyées des affectations actives."""

    reviews: list[Review]
    final: Decimal | None
    spread: Decimal
    divergent: bool


def summary(submission: Submission) -> Summary:
    edition = submission.edition
    reviews = list(
        Review.objects.filter(
            assignment__submission=submission,
            assignment__status=AssignmentStatus.ACTIVE,
            status=ReviewStatus.SUBMITTED,
        )
        .select_related("assignment__reviewer__profile", "suggested_type")
        .prefetch_related("scores__criterion")
        .order_by("assignment__pseudonym_rank", "id")
    )
    scored = [r for r in reviews if r.weighted_score is not None]
    spread = divergence(r.weighted_score for r in scored)
    return Summary(
        reviews=reviews,
        final=final_score(
            ((r.weighted_score, r.confidence) for r in scored),
            confidence_weighted=edition.confidence_weighted_score,
        ),
        spread=spread,
        divergent=len(scored) > 1 and spread > edition.divergence_threshold,
    )


# --- Écriture d'une évaluation ------------------------------------------------------------


def _lock(assignment: ReviewAssignment) -> ReviewAssignment:
    lock_submission(assignment.submission)
    return (
        ReviewAssignment.objects.select_for_update()
        .select_related("submission__edition", "submission__submission_type", "reviewer")
        .get(pk=assignment.pk)
    )


def _check_writable(assignment: ReviewAssignment, actor: Actor) -> None:
    """RG-03 et H13, revérifiés sous verrou : l'affectation du relecteur, active, sans conflit,
    soumission en évaluation."""
    ensure_editable(assignment.submission.edition)
    user = actor.user if actor.kind == ActorKind.USER else None
    if user is None or user.pk != assignment.reviewer_id:
        raise RuleViolation(code=ErrorCode.REVIEW_NOT_OPEN)
    allowed = reviewable_assignments(actor.user, assignment.submission.edition)
    if not allowed.filter(pk=assignment.pk).exists():
        raise RuleViolation(
            _("Cette évaluation n'est plus modifiable."), code=ErrorCode.REVIEW_NOT_OPEN
        )


def _decimal(value: Any) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError from error
    if not number.is_finite():
        raise ValueError
    return number


def _clean(grid: EvaluationGrid, edition: Edition, data: Mapping[str, Any]) -> dict[str, Any]:
    """Valide la copie de travail ; les erreurs sont groupées par champ."""
    errors: dict[str, list[str]] = {}
    criteria = {criterion.code: criterion for criterion in grid.criteria.all()}
    scores: dict[str, Decimal] = {}
    raw = data.get("scores") or {}
    if not isinstance(raw, Mapping):
        errors["scores"] = [_("Notes attendues par code de critère.")]
        raw = {}
    for code, value in raw.items():
        if code not in criteria:
            message = _("Critère inconnu : %(code)s.") % {"code": code}
            errors.setdefault("scores", []).append(message)
            continue
        if value is None or value == "":
            continue
        try:
            number = _decimal(value)
        except ValueError:
            errors.setdefault("scores", []).append(_("Note invalide : %(code)s.") % {"code": code})
            continue
        if (
            number != number.quantize(Decimal("0.1"))
            or not grid.scale_min <= number <= grid.scale_max
        ):
            errors.setdefault("scores", []).append(
                _("Note de %(code)s entre %(min)s et %(max)s, une décimale au plus.")
                % {"code": code, "min": grid.scale_min, "max": grid.scale_max}
            )
            continue
        scores[code] = number.quantize(Decimal("0.1"))
    cleaned: dict[str, Any] = {"scores": scores}
    recommendation = data.get("recommendation") or ""
    if recommendation and recommendation not in Recommendation.values:
        errors["recommendation"] = [_("Recommandation inconnue.")]
    cleaned["recommendation"] = recommendation
    confidence = data.get("confidence")
    if confidence in (None, ""):
        cleaned["confidence"] = None
    elif (
        isinstance(confidence, bool) or not isinstance(confidence, int) or not 1 <= confidence <= 5
    ):
        errors["confidence"] = [_("Confiance de 1 à 5.")]
    else:
        cleaned["confidence"] = confidence
    for name in ("comment_to_authors", "comment_to_committee"):
        text = data.get(name) or ""
        if not isinstance(text, str) or len(text) > COMMENT_MAX:
            errors[name] = [_("Texte de %(max)s caractères au plus.") % {"max": COMMENT_MAX}]
            text = ""
        cleaned[name] = text.strip()
    for name in ("ethics_flag", "plagiarism_flag"):
        cleaned[name] = bool(data.get(name, False))
    code = data.get("suggested_type") or None
    cleaned["suggested_type"] = None
    if code is not None:
        suggested = SubmissionType.objects.filter(edition=edition, code=code).first()
        if suggested is None:
            errors["suggested_type"] = [_("Type de communication inconnu.")]
        cleaned["suggested_type"] = suggested
    if errors:
        raise Invalid(fields=errors)
    return cleaned


def _missing(grid: EvaluationGrid, review: Review, scores: Mapping[str, Decimal]) -> dict:
    """Complétude exigée à l'envoi (H5)."""
    missing: dict[str, list[str]] = {}
    required = [c.code for c in grid.criteria.all() if c.is_required and c.code not in scores]
    if required:
        missing["scores"] = [_("Critères à noter : %(codes)s.") % {"codes": ", ".join(required)}]
    if not review.recommendation:
        missing["recommendation"] = [_("Recommandation obligatoire.")]
    if review.confidence is None:
        missing["confidence"] = [_("Confiance obligatoire.")]
    if not review.comment_to_authors:
        missing["comment_to_authors"] = [_("Commentaire aux auteurs obligatoire.")]
    return missing


def _write(assignment: ReviewAssignment, data: Mapping[str, Any] | None) -> Review:
    submission = assignment.submission
    review = Review.objects.filter(assignment=assignment).select_related("grid").first()
    if review is None:
        grid = grid_for(submission.edition, submission.submission_type)
        if grid is None:
            raise RuleViolation(
                _("Aucune grille d'évaluation : prévenez le président du comité scientifique."),
                code=ErrorCode.REVIEW_NOT_OPEN,
            )
        review = Review(assignment=assignment, grid=grid)
    grid = review.grid
    if data is None:
        return review
    cleaned = _clean(grid, submission.edition, data)
    for name in REVIEW_FIELDS:
        setattr(review, name, cleaned[name])
    review.suggested_type = cleaned["suggested_type"]
    scores = cleaned["scores"]
    review.weighted_score = _score(grid, scores)
    review.save()
    ReviewScore.objects.filter(review=review).exclude(criterion__code__in=list(scores)).delete()
    by_code = {criterion.code: criterion for criterion in grid.criteria.all()}
    for code, value in scores.items():
        ReviewScore.objects.update_or_create(
            review=review, criterion=by_code[code], defaults={"value": value}
        )
    lock_grid(grid)
    return review


def _score(grid: EvaluationGrid, scores: Mapping[str, Decimal]) -> Decimal | None:
    criteria = [
        CriterionWeight(key=c.code, weight=c.weight, required=c.is_required)
        for c in grid.criteria.all()
    ]
    return weighted_score(criteria, scores, grid.scale_min, grid.scale_max)


@transaction.atomic
def save_review(assignment: ReviewAssignment, data: Mapping[str, Any], *, actor: Actor) -> Review:
    """Enregistre le brouillon (copie complète). Une évaluation envoyée ne se modifie que par
    un nouvel envoi (RG-06)."""
    assignment = _lock(assignment)
    _check_writable(assignment, actor)
    current = Review.objects.filter(assignment=assignment).first()
    if current is not None and current.status == ReviewStatus.SUBMITTED:
        raise RuleViolation(
            _("Évaluation envoyée : renvoyez-la pour la modifier."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    return _write(assignment, data)


def _snapshot(review: Review) -> dict[str, Any]:
    return {
        "scores": {code: str(value) for code, value in sorted(scores_of(review).items())},
        "weighted_score": str(review.weighted_score) if review.weighted_score is not None else None,
        "recommendation": review.recommendation,
        "confidence": review.confidence,
        "comment_to_authors": review.comment_to_authors,
        "comment_to_committee": review.comment_to_committee,
        "ethics_flag": review.ethics_flag,
        "plagiarism_flag": review.plagiarism_flag,
        "suggested_type": review.suggested_type.code if review.suggested_type else None,
    }


@transaction.atomic
def submit_review(
    assignment: ReviewAssignment,
    data: Mapping[str, Any] | None,
    *,
    actor: Actor,
    now: datetime | None = None,
) -> Review:
    """Envoie l'évaluation (premier envoi ou modification après envoi, RG-06) : version en
    ajout seul, puis RG-07, ouverture de la discussion et contrôle de divergence."""
    now = now or timezone.now()
    assignment = _lock(assignment)
    _check_writable(assignment, actor)
    review = _write(assignment, data)
    if review.pk is None:
        raise Invalid(fields={"scores": [_("Évaluation vide.")]})
    review.refresh_from_db()
    missing = _missing(review.grid, review, scores_of(review))
    if missing:
        raise Invalid(_("Évaluation incomplète."), fields=missing)
    first = review.status != ReviewStatus.SUBMITTED
    review.status = ReviewStatus.SUBMITTED
    review.version += 1
    review.submitted_at = now
    review.save(update_fields=["status", "version", "submitted_at", "updated_at"])
    ReviewVersion.objects.create(
        review=review, version=review.version, at=now, snapshot=_snapshot(review)
    )
    submission = assignment.submission
    record(
        "review.submitted" if first else "review.resubmitted",
        actor=actor,
        edition=submission.edition,
        obj=review,
        after={
            "submission": submission.reference,
            "version": review.version,
            "weighted_score": review.weighted_score,
        },
    )
    _after_submission(submission, now)
    return review


def _after_submission(submission: Submission, now: datetime) -> None:
    submission = Submission.objects.select_related("edition").get(pk=submission.pk)
    edition = submission.edition
    count = submitted_count(submission)
    if submission.status == S.UNDER_REVIEW and count >= edition.reviewers_per_submission:
        workflow.transition(submission, S.REVIEWED, Actor.system("review:rg07"), now=now)
    active = ReviewAssignment.objects.filter(
        submission=submission, status=AssignmentStatus.ACTIVE
    ).count()
    if count and count == active:
        open_discussion(submission, actor=Actor.system("review:rg08"), now=now)
    state = summary(submission)
    if state.divergent:
        from apps.reviews.notifications import divergence_detected

        for chair in presidents(edition):
            divergence_detected(submission, chair, state.spread)


def presidents(edition: Edition) -> list[User]:
    """Destinataires des signalements : présidents du CS, sinon présidents de la conférence."""
    for role in (Role.SC_CHAIR, Role.CHAIR):
        users = [
            row.user
            for row in UserRole.objects.filter(
                edition=edition, role=role, status=UserRoleStatus.ACTIVE
            ).select_related("user")
        ]
        if users:
            return users
    return []


# --- Refus du relecteur ---------------------------------------------------------------------


@transaction.atomic
def decline(
    assignment: ReviewAssignment, *, reason: str, conflict: bool, actor: Actor
) -> ReviewAssignment:
    """Le relecteur décline (motif obligatoire), en déclarant au besoin un conflit (H8) ; le
    président du CS en est informé pour désigner un remplaçant (H15)."""
    assignment = _lock(assignment)
    _check_writable(assignment, actor)
    reason = reason.strip()
    if not reason:
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    review = getattr(assignment, "review", None)
    if review is not None and review.status == ReviewStatus.SUBMITTED:
        raise RuleViolation(
            _("Évaluation déjà envoyée : demandez au président de l'écarter."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    submission = assignment.submission
    end_assignment(assignment, AssignmentStatus.DECLINED, reason=reason, actor=actor)
    if conflict:
        row, _created = ConflictOfInterest.objects.update_or_create(
            submission=submission,
            reviewer=assignment.reviewer,
            kind=ConflictKind.DECLARED,
            defaults={
                "source": ConflictSource.REVIEWER,
                "reason": reason,
                "declared_by": assignment.reviewer,
                "overridden_by": None,
                "overridden_at": None,
                "overridden_reason": "",
            },
        )
        record(
            "review.conflict_declared",
            actor=actor,
            edition=submission.edition,
            obj=row,
            after={
                "submission": submission.reference,
                "reviewer": assignment.reviewer_id,
                "source": ConflictSource.REVIEWER,
            },
            reason=reason,
        )
    from apps.reviews.notifications import assignment_declined

    for chair in presidents(submission.edition):
        assignment_declined(assignment, chair)
    return assignment


# --- Discussion (RG-08) ---------------------------------------------------------------------


def open_discussion(
    submission: Submission, *, actor: Actor, now: datetime | None = None
) -> Discussion:
    """Ouvre la discussion (idempotent) ; journalisé à l'ouverture."""
    now = now or timezone.now()
    discussion, created = Discussion.objects.get_or_create(
        submission=submission,
        defaults={
            "opened_at": now,
            "opened_by": actor.user if actor.kind == ActorKind.USER else None,
        },
    )
    if created:
        record(
            "review.discussion_opened",
            actor=actor,
            edition=submission.edition,
            obj=discussion,
            after={"submission": submission.reference},
        )
    return discussion


@transaction.atomic
def open_discussion_by_chair(submission: Submission, *, actor: Actor) -> Discussion:
    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    if submission.status not in REVIEWABLE:
        raise RuleViolation(code=ErrorCode.REVIEW_NOT_OPEN)
    return open_discussion(submission, actor=actor)


def _clean_body(body: str) -> str:
    body = (body or "").strip()
    if not body or len(body) > MESSAGE_MAX:
        raise Invalid(
            fields={"body": [_("Message de 1 à %(max)s caractères.") % {"max": MESSAGE_MAX}]}
        )
    return body


@transaction.atomic
def post_message(
    submission: Submission,
    body: str,
    *,
    actor: Actor,
    assignment: ReviewAssignment | None = None,
) -> DiscussionMessage:
    """Message de discussion : d'un relecteur (``assignment`` : RG-08 revérifié) ou du
    président. Discussion ouverte, soumission en évaluation."""
    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    if submission.status not in REVIEWABLE:
        raise RuleViolation(code=ErrorCode.REVIEW_NOT_OPEN)
    if assignment is not None:
        assignment = ReviewAssignment.objects.select_related("submission", "review").get(
            pk=assignment.pk
        )
        if not can_edit(assignment) or not can_see_discussion(assignment):
            raise RuleViolation(code=ErrorCode.DISCUSSION_CLOSED)
    discussion = Discussion.objects.filter(submission=submission).first()
    if discussion is None:
        raise RuleViolation(code=ErrorCode.DISCUSSION_CLOSED)
    if actor.kind != ActorKind.USER or actor.user is None:
        raise RuleViolation(code=ErrorCode.DISCUSSION_CLOSED)
    return DiscussionMessage.objects.create(
        discussion=discussion, author=actor.user, body=_clean_body(body), at=timezone.now()
    )


def pseudonyms(submission: Submission) -> dict[int, int]:
    """Relecteur → rang de pseudonyme (H11), toutes affectations confondues (le plus récent)."""
    ranks: dict[int, int] = {}
    for reviewer_id, rank in (
        ReviewAssignment.objects.filter(submission=submission)
        .order_by("assigned_at", "id")
        .values_list("reviewer_id", "pseudonym_rank")
    ):
        ranks[reviewer_id] = rank
    return ranks


# --- Suivi (président) ----------------------------------------------------------------------


def progress(edition: Edition, *, now: datetime | None = None) -> dict[str, Any]:
    """Suivi de l'évaluation : charge et retards par relecteur, avancement par thématique,
    soumissions divergentes (H12). Nombre fixe de requêtes."""
    now = now or timezone.now()
    in_edition = Q(review_assignments__submission__edition=edition)
    active = in_edition & Q(review_assignments__status=AssignmentStatus.ACTIVE)
    submitted = active & Q(review_assignments__review__status=ReviewStatus.SUBMITTED)
    pending = Q(review_assignments__review__isnull=True) | Q(
        review_assignments__review__status=ReviewStatus.DRAFT
    )
    late = (
        active
        & pending
        & Q(review_assignments__due_at__lt=now)
        & Q(review_assignments__submission__status__in=REVIEWABLE)
    )
    reviewers = (
        reviewers_of(edition)
        .select_related("profile")
        .annotate(
            active_count=Count("review_assignments", filter=active, distinct=True),
            submitted_count=Count("review_assignments", filter=submitted, distinct=True),
            late_count=Count("review_assignments", filter=late, distinct=True),
        )
        .order_by("profile__last_name", "profile__first_name", "id")
    )
    tracks: dict[str | None, dict[str, Any]] = {}
    rows = (
        Submission.objects.filter(edition=edition, status__in=REVIEWABLE)
        .values("track__code", "status")
        .annotate(count=Count("id"))
        .order_by("track__code")
    )
    for row in rows:
        entry = tracks.setdefault(
            row["track__code"], {"code": row["track__code"], "in_review": 0, "reviewed": 0}
        )
        entry["in_review"] += row["count"]
        if row["status"] == S.REVIEWED:
            entry["reviewed"] += row["count"]
    scores: dict[int, list[Decimal]] = defaultdict(list)
    for submission_id, score in Review.objects.filter(
        assignment__submission__edition=edition,
        assignment__submission__status__in=REVIEWABLE,
        assignment__status=AssignmentStatus.ACTIVE,
        status=ReviewStatus.SUBMITTED,
        weighted_score__isnull=False,
    ).values_list("assignment__submission_id", "weighted_score"):
        scores[submission_id].append(score)
    spreads = {pk: divergence(values) for pk, values in scores.items() if len(values) > 1}
    over = {pk: spread for pk, spread in spreads.items() if spread > edition.divergence_threshold}
    divergent = [
        {"id": row.pk, "reference": row.reference, "title": row.title, "spread": over[row.pk]}
        for row in Submission.objects.filter(pk__in=over).order_by("reference", "id")
    ]
    return {
        "threshold": edition.divergence_threshold,
        "reviewers": [
            {
                "id": user.pk,
                "name": display_name(user),
                "active": user.active_count,
                "submitted": user.submitted_count,
                "late": user.late_count,
            }
            for user in reviewers
        ],
        "tracks": list(tracks.values()),
        "divergent": divergent,
    }
