"""Recevabilité, affectations, charge, échéances et expertises (plan L4, H6, H7, H10, H14,
H15 ; RG-03).

- **Recevabilité** (H10) : ``SCREENING → REJECTED`` motivé, ou ``SCREENING → UNDER_REVIEW``
  quand les relecteurs requis (``reviewers_per_submission``) sont affectés ; les deux par
  ``transition()`` (règle n° 4), qui revérifie la capacité ``reviews.manage``.
- **Affectation** (H6) : manuelle, par un membre du comité scientifique de l'édition
  (``SC_MEMBER`` ou ``SC_CHAIR``) ; refusée en cas de conflit non levé (H8) ou au-delà de la
  charge maximale de l'édition ; échéance par défaut : la date clé ``review_deadline``.
  Le relecteur est prévenu quand l'évaluation s'ouvre (``UNDER_REVIEW``), ou tout de suite si
  elle l'est déjà.
- **Pseudonyme** (H11) : rang tiré au hasard parmi les rangs libres de la soumission, stable
  (un relecteur remplacé garde le sien) ; l'ordre d'affectation n'est pas révélé.
"""

from __future__ import annotations

import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, QuerySet
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import CAPABILITIES, Capability
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, KeyDateCode, Track
from apps.conferences.services import key_date, local_to_utc
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.reviews.models import (
    AssignmentStatus,
    ConflictKind,
    ConflictOfInterest,
    ReviewAssignment,
    ReviewerTrack,
    ReviewStatus,
)
from apps.reviews.services.conflicts import (
    Conflict,
    ConflictDetector,
    blocking_conflicts,
    override_conflicts,
)
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

# Rôles qui évaluent (capacité ``reviews.write``) : SC_MEMBER et SC_CHAIR (H19).
REVIEWER_ROLES: frozenset[str] = frozenset(
    role for role, capabilities in CAPABILITIES.items() if Capability.REVIEWS_WRITE in capabilities
)
# Statuts où l'on affecte (un relecteur supplémentaire après REVIEWED ne fait pas revenir en
# arrière, H14), où le relecteur a été prévenu, où il évalue (RG-03).
ASSIGNABLE = (S.SCREENING, S.UNDER_REVIEW, S.REVIEWED)
NOTIFIED = (S.UNDER_REVIEW, S.REVIEWED)
REVIEWABLE = (S.UNDER_REVIEW, S.REVIEWED)
# Le relecteur relit son évaluation après la décision (lecture seule).
VISIBLE = (
    *REVIEWABLE,
    S.ACCEPTED,
    S.ACCEPTED_MINOR,
    S.WAITLIST,
    S.REJECTED,
    S.CAMERA_READY_RECEIVED,
    S.CONFIRMED,
    S.SCHEDULED,
    S.PRESENTED,
    S.PUBLISHED,
    S.WITHDRAWN,
)

CONFLICT_LABELS = {
    ConflictKind.AUTHOR: gettext_lazy("Le relecteur est auteur de la soumission."),
    ConflictKind.INSTITUTION: gettext_lazy("Le relecteur est de la même institution qu'un auteur."),
    ConflictKind.DECLARED: gettext_lazy("Un conflit d'intérêts a été déclaré."),
}


def lock_submission(submission: Submission) -> Submission:
    """Verrou de la soumission : affectations, annulations et recevabilité en série."""
    return Submission.objects.select_for_update().select_related("edition").get(pk=submission.pk)


def _writable(edition: Edition, actor: Actor) -> None:
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)


def reviewers_of(edition: Edition) -> QuerySet[User]:
    """Comptes qui évaluent dans l'édition (rôle actif ``SC_MEMBER`` ou ``SC_CHAIR``)."""
    return User.objects.filter(
        roles__edition=edition,
        roles__status=UserRoleStatus.ACTIVE,
        roles__role__in=REVIEWER_ROLES,
    ).distinct()


def active_key(submission_id: int, reviewer_id: int) -> str:
    return f"{submission_id}:{reviewer_id}"


def _due_at(edition: Edition, due_local: datetime | None, now: datetime) -> datetime | None:
    """Échéance (D13 : saisie à l'heure de l'édition) ; par défaut ``review_deadline``."""
    if due_local is None:
        due = key_date(edition, KeyDateCode.REVIEW_DEADLINE)
        if due is not None and due <= now:
            raise Invalid(
                fields={
                    "due_local": [
                        _("La date de fin des évaluations est passée : indiquez une échéance.")
                    ]
                }
            )
        return due
    try:
        due = local_to_utc(due_local, edition.timezone)
    except Invalid as error:
        raise Invalid(fields={"due_local": error.fields.get("at_local", [])}) from error
    if due <= now:
        raise Invalid(fields={"due_local": [_("Échéance dans le futur attendue.")]})
    return due


def _pseudonym_rank(submission: Submission) -> int:
    """H11 : rang libre tiré au hasard, parmi au moins ``reviewers_per_submission`` rangs."""
    used = set(
        ReviewAssignment.objects.filter(submission=submission).values_list(
            "pseudonym_rank", flat=True
        )
    )
    size = max(submission.edition.reviewers_per_submission, len(used) + 1)
    return secrets.choice([rank for rank in range(1, size + 1) if rank not in used])


def _conflict_error(conflicts: list[Conflict]) -> RuleViolation:
    return RuleViolation(
        _("Conflit d'intérêts."),
        code=ErrorCode.CONFLICT_OF_INTEREST,
        fields={"reviewer": [CONFLICT_LABELS[conflict.kind] for conflict in conflicts]},
    )


@transaction.atomic
def assign(
    submission: Submission,
    reviewer: User,
    *,
    actor: Actor,
    due_local: datetime | None = None,
    override_reason: str = "",
    now: datetime | None = None,
) -> ReviewAssignment:
    """Affecte ``reviewer`` à ``submission`` (H6). Un conflit levable n'est levé qu'avec un
    motif (``override_reason``), la vue ayant exigé une réauthentification récente ; un conflit
    d'auteur ne l'est jamais. Droit ``reviews.manage`` vérifié par la vue (règle n° 2)."""
    now = now or timezone.now()
    submission = lock_submission(submission)
    edition = submission.edition
    _writable(edition, actor)
    if submission.status not in ASSIGNABLE:
        raise RuleViolation(
            _("Affectation impossible à ce stade de la soumission."),
            code=ErrorCode.REVIEW_NOT_OPEN,
        )
    # Verrou des rôles du relecteur : vérifie qu'il évalue dans l'édition et sérialise le
    # contrôle de charge entre deux affectations simultanées.
    roles = UserRole.objects.select_for_update().filter(
        user=reviewer,
        edition=edition,
        status=UserRoleStatus.ACTIVE,
        role__in=REVIEWER_ROLES,
    )
    if not list(roles):
        raise Invalid(
            fields={"reviewer": [_("Ce compte n'est pas membre du comité scientifique.")]}
        )
    if ReviewAssignment.objects.filter(
        submission=submission, reviewer=reviewer, status=AssignmentStatus.ACTIVE
    ).exists():
        raise Invalid(fields={"reviewer": [_("Ce relecteur est déjà affecté.")]})
    conflicts = blocking_conflicts(submission, reviewer)
    override_reason = override_reason.strip()
    if any(not c.overridable for c in conflicts) or (conflicts and not override_reason):
        raise _conflict_error(conflicts)
    load = ReviewAssignment.objects.filter(
        reviewer=reviewer, submission__edition=edition, status=AssignmentStatus.ACTIVE
    ).count()
    if load >= edition.max_reviews_per_reviewer:
        raise RuleViolation(
            _("Charge maximale atteinte (%(max)s évaluations).")
            % {"max": edition.max_reviews_per_reviewer},
            code=ErrorCode.REVIEWER_OVERLOADED,
        )
    due_at = _due_at(edition, due_local, now)
    if conflicts:
        override_conflicts(submission, reviewer, conflicts, reason=override_reason, actor=actor)
    assignment = ReviewAssignment.objects.create(
        submission=submission,
        reviewer=reviewer,
        assigned_by=actor.user if actor.kind == ActorKind.USER else None,
        assigned_at=now,
        due_at=due_at,
        conflict_override_reason=override_reason if conflicts else "",
        pseudonym_rank=_pseudonym_rank(submission),
        active_key=active_key(submission.pk, reviewer.pk),
    )
    record(
        "review.assigned",
        actor=actor,
        edition=edition,
        obj=assignment,
        after={
            "submission": submission.reference,
            "reviewer": reviewer.pk,
            "due_at": due_at,
            "conflicts_overridden": [conflict.kind for conflict in conflicts],
        },
        reason=override_reason if conflicts else "",
    )
    if submission.status in NOTIFIED:
        from apps.reviews.notifications import assignment_opened

        assignment_opened(assignment)
    return assignment


def end_assignment(
    assignment: ReviewAssignment, status: str, *, reason: str, actor: Actor
) -> ReviewAssignment:
    """Termine une affectation active (annulée ou déclinée), dans la transaction de
    l'appelant ; la clé active est libérée. Le relecteur prévenu d'une annulation en est
    informé."""
    assignment.status = status
    assignment.active_key = None
    assignment.reason = reason
    assignment.save(update_fields=["status", "active_key", "reason", "updated_at"])
    submission = Submission.objects.select_related("edition").get(pk=assignment.submission_id)
    record(
        f"review.assignment_{status}",
        actor=actor,
        edition=submission.edition,
        obj=assignment,
        after={"submission": submission.reference, "reviewer": assignment.reviewer_id},
        reason=reason,
    )
    if status == AssignmentStatus.CANCELLED and submission.status in NOTIFIED:
        from apps.reviews.notifications import assignment_cancelled

        assignment_cancelled(assignment)
    return assignment


def _lock_assignment(assignment: ReviewAssignment) -> ReviewAssignment:
    lock_submission(assignment.submission)
    return (
        ReviewAssignment.objects.select_for_update()
        .select_related("submission__edition", "reviewer")
        .get(pk=assignment.pk)
    )


def _check_open(assignment: ReviewAssignment) -> None:
    if assignment.status != AssignmentStatus.ACTIVE:
        raise RuleViolation(_("Cette affectation est terminée."), code=ErrorCode.INVALID_TRANSITION)
    if assignment.submission.status not in ASSIGNABLE:
        raise RuleViolation(code=ErrorCode.REVIEW_NOT_OPEN)


@transaction.atomic
def cancel_assignment(
    assignment: ReviewAssignment, *, reason: str, actor: Actor
) -> ReviewAssignment:
    """Annulation motivée par le président (remplacement, H15). Une évaluation envoyée
    compte : on ne l'écarte qu'en déclarant un conflit."""
    assignment = _lock_assignment(assignment)
    _writable(assignment.submission.edition, actor)
    _check_open(assignment)
    reason = reason.strip()
    if not reason:
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    review = getattr(assignment, "review", None)
    if review is not None and review.status == ReviewStatus.SUBMITTED:
        raise RuleViolation(
            _("Évaluation déjà envoyée : déclarez un conflit pour l'écarter."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    return end_assignment(assignment, AssignmentStatus.CANCELLED, reason=reason, actor=actor)


@transaction.atomic
def change_due_date(
    assignment: ReviewAssignment, *, due_local: datetime, actor: Actor
) -> ReviewAssignment:
    """Nouvelle échéance (H6) ; les relances repartent de zéro (H15)."""
    assignment = _lock_assignment(assignment)
    edition = assignment.submission.edition
    _writable(edition, actor)
    _check_open(assignment)
    due_at = _due_at(edition, due_local, timezone.now())
    before = assignment.due_at
    assignment.due_at = due_at
    assignment.reminders = []
    assignment.save(update_fields=["due_at", "reminders", "updated_at"])
    record(
        "review.assignment_updated",
        actor=actor,
        edition=edition,
        obj=assignment,
        before={"due_at": before},
        after={"due_at": due_at},
    )
    return assignment


# --- Recevabilité (H10) -----------------------------------------------------------------------


def screen(submission: Submission, *, admissible: bool, reason: str, actor: Actor) -> Submission:
    """Recevable : ``UNDER_REVIEW`` (relecteurs requis affectés) ; sinon ``REJECTED`` motivé."""
    target = S.UNDER_REVIEW if admissible else S.REJECTED
    return workflow.transition(submission, target, actor, reason=reason)


def submitted_count(submission: Submission) -> int:
    """Évaluations envoyées des affectations actives (RG-07)."""
    return ReviewAssignment.objects.filter(
        submission=submission,
        status=AssignmentStatus.ACTIVE,
        review__status=ReviewStatus.SUBMITTED,
    ).count()


def guard_review_steps(submission: Submission, to_state: str, now: datetime) -> None:
    """Gardes du workflow : l'évaluation ne s'ouvre qu'avec les relecteurs requis (H10) ; la
    soumission n'est évaluée qu'avec le nombre requis d'évaluations envoyées (RG-07)."""
    required = submission.edition.reviewers_per_submission
    if to_state == S.UNDER_REVIEW:
        count = ReviewAssignment.objects.filter(
            submission=submission, status=AssignmentStatus.ACTIVE
        ).count()
        if count < required:
            raise RuleViolation(
                _("%(count)s relecteur(s) affecté(s) sur %(required)s requis.")
                % {"count": count, "required": required},
                code=ErrorCode.REVIEWERS_MISSING,
            )
    elif to_state == S.REVIEWED and submitted_count(submission) < required:
        raise RuleViolation(
            _("Évaluations envoyées insuffisantes (RG-07)."), code=ErrorCode.INVALID_TRANSITION
        )


def on_transition(submission: Submission, from_state: str, to_state: str, actor: Actor) -> None:
    """Effet du workflow : ouverture de l'évaluation → relecteurs prévenus ; rejet de
    recevabilité → affectations annulées (relecteurs jamais prévenus, aucun e-mail)."""
    if from_state != S.SCREENING:
        return
    active = list(
        ReviewAssignment.objects.filter(
            submission_id=submission.pk, status=AssignmentStatus.ACTIVE
        ).select_related("reviewer")
    )
    if to_state == S.UNDER_REVIEW:
        from apps.reviews.notifications import assignment_opened

        for assignment in active:
            assignment_opened(assignment)
    elif to_state == S.REJECTED:
        for assignment in active:
            end_assignment(
                assignment,
                AssignmentStatus.CANCELLED,
                reason=_("Soumission non recevable."),
                actor=actor,
            )


# --- RG-03 ------------------------------------------------------------------------------------


def reviewer_assignments(
    user: User, edition: Edition, statuses: tuple[str, ...] = REVIEWABLE
) -> QuerySet[ReviewAssignment]:
    """Affectations actives de ``user`` dont la soumission est dans ``statuses``, sans conflit
    déclaré non levé, jamais sur une soumission dont il est auteur (défense en profondeur :
    l'affectation et la déclaration l'empêchent déjà)."""
    declared = ConflictOfInterest.objects.filter(
        submission=OuterRef("submission"),
        reviewer=user,
        kind=ConflictKind.DECLARED,
        overridden_at__isnull=True,
    )
    return (
        ReviewAssignment.objects.filter(
            reviewer=user,
            status=AssignmentStatus.ACTIVE,
            submission__edition=edition,
            submission__status__in=statuses,
        )
        .exclude(Exists(declared))
        .exclude(submission__submitter=user)
        .exclude(submission__authors__user=user)
    )


def reviewable_assignments(user: User, edition: Edition) -> QuerySet[ReviewAssignment]:
    """RG-03 : affectations où ``user`` évalue — actives, soumission en évaluation, aucun
    conflit déclaré non levé."""
    return reviewer_assignments(user, edition, REVIEWABLE)


# --- Candidats et expertises (H6, H7) ---------------------------------------------------------


@dataclass
class Candidate:
    user: User
    load: int
    tracks: list[str] = field(default_factory=list)
    assignment: ReviewAssignment | None = None
    conflicts: list[Conflict] = field(default_factory=list)


def candidates(submission: Submission) -> list[Candidate]:
    """Relecteurs de l'édition pour ``submission`` : charge, expertises, affectation en cours,
    conflits (détectés ou déclarés, levés ou non). Nombre fixe de requêtes."""
    edition = submission.edition
    users = list(
        reviewers_of(edition)
        .select_related("profile")
        .order_by("profile__last_name", "profile__first_name", "id")
    )
    loads = dict(
        ReviewAssignment.objects.filter(
            submission__edition=edition, status=AssignmentStatus.ACTIVE, reviewer__in=users
        )
        .order_by()
        .values("reviewer")
        .annotate(count=Count("id"))
        .values_list("reviewer", "count")
    )
    tracks: dict[int, list[str]] = defaultdict(list)
    for user_id, code in (
        ReviewerTrack.objects.filter(edition=edition, user__in=users)
        .order_by("track__position", "track_id")
        .values_list("user_id", "track__code")
    ):
        tracks[user_id].append(code)
    assigned = {
        row.reviewer_id: row
        for row in ReviewAssignment.objects.filter(
            submission=submission, status=AssignmentStatus.ACTIVE
        )
    }
    detector = ConflictDetector(submission, users)
    return [
        Candidate(
            user=user,
            load=loads.get(user.pk, 0),
            tracks=tracks[user.pk],
            assignment=assigned.get(user.pk),
            conflicts=detector.conflicts(user),
        )
        for user in users
    ]


@transaction.atomic
def set_expertise(user: User, edition: Edition, tracks: list[Track], *, actor: Actor) -> None:
    """Thématiques de compétence déclarées par le relecteur pour l'édition (H7)."""
    _writable(edition, actor)
    if not reviewers_of(edition).filter(pk=user.pk).exists():
        raise NotAllowed()
    if any(track.edition_id != edition.pk for track in tracks):
        raise Invalid(fields={"tracks": [_("Thématique d'une autre édition.")]})
    wanted = {track.pk for track in tracks}
    current = ReviewerTrack.objects.filter(user=user, edition=edition)
    current.exclude(track_id__in=wanted).delete()
    existing = set(current.values_list("track_id", flat=True))
    ReviewerTrack.objects.bulk_create(
        ReviewerTrack(user=user, edition=edition, track_id=track_id)
        for track_id in sorted(wanted - existing)
    )
