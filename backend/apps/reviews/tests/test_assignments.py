"""Lot L4, étape L4.2 : recevabilité (H10), affectations (H6), conflits (H8, RG-03), charge,
pseudonymes (H11), expertises (H7)."""

from __future__ import annotations

import datetime as dt

import pytest
from allauth.account.models import EmailAddress
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import RoleSource, UserRole
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import make_member
from apps.communications.models import Notification, NotificationKind, OutboxEmail
from apps.conferences.models import EditionStatus, KeyDateCode
from apps.conferences.tests.factories import KeyDateFactory, TrackFactory
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.core.integrity import integrity_checks
from apps.core.models import AuditLog
from apps.reviews.integrity import check_assignments
from apps.reviews.models import (
    AssignmentStatus,
    ConflictKind,
    ConflictOfInterest,
    ConflictSource,
    Review,
    ReviewAssignment,
    ReviewerTrack,
    ReviewStatus,
)
from apps.reviews.services import assignments as service
from apps.reviews.services.conflicts import (
    blocking_conflicts,
    declare_conflict,
    normalized_institution,
)
from apps.reviews.services.grids import create_grid
from apps.reviews.tests.helpers import in_status, reviewer, screening_submission
from apps.submissions.models import StatusHistory, SubmissionAuthor
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import author_user, complete_submission, user_actor

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def setup():
    submission = screening_submission()
    edition = submission.edition
    chair = make_member(edition, Role.SC_CHAIR)
    return submission, edition, user_actor(chair)


def assign(submission, user, actor, **kwargs):
    return service.assign(submission, user, actor=actor, **kwargs)


def emails(template: str) -> list[OutboxEmail]:
    return list(OutboxEmail.objects.filter(template_code=template).order_by("id"))


# --- Recevabilité (H10) -------------------------------------------------------------------


def test_h10_screening_reject_requires_a_reason_and_notifies_the_submitter(setup):
    submission, edition, actor = setup
    active = assign(submission, reviewer(edition), actor)
    with pytest.raises(Invalid) as error:
        service.screen(submission, admissible=False, reason=" ", actor=actor)
    assert "reason" in error.value.fields
    service.screen(submission, admissible=False, reason="Hors du champ", actor=actor)
    submission.refresh_from_db()
    assert submission.status == S.REJECTED
    assert StatusHistory.objects.get(to_status=S.REJECTED).reason == "Hors du champ"
    (mail,) = emails("submission/email/screening_rejected")
    assert mail.to_email == submission.submitter.email
    assert "Hors du champ" in mail.body_text
    assert Notification.objects.get(user=submission.submitter).kind == (
        NotificationKind.SCREENING_REJECTED
    )
    # Affectations annulées sans e-mail : le relecteur n'avait pas été prévenu.
    active.refresh_from_db()
    assert (active.status, active.active_key) == (AssignmentStatus.CANCELLED, None)
    assert not emails("review/email/cancelled")


def test_h10_admissible_requires_the_reviewers_then_notifies_them(setup):
    submission, edition, actor = setup
    edition.reviewers_per_submission = 2
    edition.save()
    first = reviewer(edition)
    assign(submission, first, actor)
    with pytest.raises(RuleViolation) as error:
        service.screen(submission, admissible=True, reason="", actor=actor)
    assert error.value.code == ErrorCode.REVIEWERS_MISSING
    assert not emails("review/email/assigned")
    assign(submission, reviewer(edition), actor)
    service.screen(submission, admissible=True, reason="", actor=actor)
    submission.refresh_from_db()
    assert submission.status == S.UNDER_REVIEW
    sent = emails("review/email/assigned")
    assert len(sent) == 2
    # RG-04 : l'e-mail au relecteur ne nomme pas les auteurs.
    assert all("Mensah" not in mail.body_text and "Kofi" not in mail.body_text for mail in sent)
    assert submission.reference in sent[0].body_text


@pytest.mark.parametrize("role", [Role.SC_MEMBER, Role.OC_MEMBER, Role.AUTHOR])
def test_h10_screening_needs_reviews_manage_checked_by_the_workflow(setup, role):
    """Règle n° 2 : la capacité est revérifiée par ``transition()``, pas seulement la vue."""
    submission, edition, _actor = setup
    member = make_member(edition, role)
    with pytest.raises(NotAllowed):
        service.screen(submission, admissible=False, reason="Non", actor=user_actor(member))
    with pytest.raises(NotAllowed):
        service.screen(submission, admissible=False, reason="Non", actor=Actor.system("job:x"))
    stranger = make_member(complete_submission().edition, Role.SC_CHAIR)
    with pytest.raises(NotAllowed):
        service.screen(submission, admissible=False, reason="Non", actor=user_actor(stranger))
    submission.refresh_from_db()
    assert submission.status == S.SCREENING


# --- Affectation (H6) ---------------------------------------------------------------------


def test_h6_assignment_defaults_audit_and_no_email_before_review_opens(setup):
    submission, edition, actor = setup
    deadline = timezone.now() + dt.timedelta(days=30)
    KeyDateFactory(edition=edition, code=KeyDateCode.REVIEW_DEADLINE, at=deadline)
    user = reviewer(edition)
    assignment = assign(submission, user, actor)
    assert assignment.status == AssignmentStatus.ACTIVE
    assert assignment.due_at == deadline
    assert assignment.active_key == f"{submission.pk}:{user.pk}"
    assert assignment.assigned_by == actor.user
    assert assignment.pseudonym_rank in {1, 2}
    entry = AuditLog.objects.get(action="review.assigned")
    assert entry.after["reviewer"] == user.pk and entry.after["conflicts_overridden"] == []
    assert not emails("review/email/assigned")


def test_h6_assignment_during_review_notifies_at_once_and_reviewed_stays(setup):
    """H14 : un relecteur supplémentaire après REVIEWED ne fait pas revenir en arrière."""
    submission, edition, actor = setup
    in_status(submission, S.REVIEWED)
    assign(submission, reviewer(edition), actor)
    submission.refresh_from_db()
    assert submission.status == S.REVIEWED
    assert len(emails("review/email/assigned")) == 1


def test_h6_assignment_refusals(setup):
    submission, edition, actor = setup
    oc = make_member(edition, Role.OC_MEMBER)
    with pytest.raises(Invalid) as error:
        assign(submission, oc, actor)
    assert "reviewer" in error.value.fields
    user = reviewer(edition)
    assign(submission, user, actor)
    with pytest.raises(Invalid):
        assign(submission, user, actor)
    draft = complete_submission(edition)
    with pytest.raises(RuleViolation) as error:
        assign(draft, reviewer(edition), actor)
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    with pytest.raises(RuleViolation) as error:
        assign(submission, reviewer(edition), actor)
    assert error.value.code == ErrorCode.EDITION_ARCHIVED


def test_h6_sc_chair_can_be_assigned_as_reviewer(setup):
    submission, edition, actor = setup
    other_chair = reviewer(edition, role=Role.SC_CHAIR)
    assert assign(submission, other_chair, actor).reviewer == other_chair


def test_h6_maximum_load_counts_active_assignments_only(setup):
    submission, edition, actor = setup
    edition.max_reviews_per_reviewer = 1
    edition.save()
    user = reviewer(edition)
    first = assign(submission, user, actor)
    other = screening_submission(edition)
    with pytest.raises(RuleViolation) as error:
        assign(other, user, actor)
    assert error.value.code == ErrorCode.REVIEWER_OVERLOADED
    service.cancel_assignment(first, reason="Remplacement", actor=actor)
    assert assign(other, user, actor).status == AssignmentStatus.ACTIVE


def test_d13_due_date_entered_in_the_edition_time_zone(setup):
    submission, edition, actor = setup
    edition.timezone = "Europe/Paris"
    edition.save()
    due = dt.datetime(2099, 5, 1, 23, 59)
    assignment = assign(submission, reviewer(edition), actor, due_local=due)
    # Heure d'été de Paris (UTC+2) : 23 h 59 locales = 21 h 59 UTC.
    assert assignment.due_at == dt.datetime(2099, 5, 1, 21, 59, tzinfo=dt.UTC)
    with pytest.raises(Invalid) as error:
        assign(submission, reviewer(edition), actor, due_local=dt.datetime(2001, 1, 1))
    assert "due_local" in error.value.fields
    KeyDateFactory(
        edition=edition,
        code=KeyDateCode.REVIEW_DEADLINE,
        at=timezone.now() - dt.timedelta(days=1),
    )
    with pytest.raises(Invalid) as error:
        assign(submission, reviewer(edition), actor)
    assert "due_local" in error.value.fields


def test_h11_pseudonym_ranks_are_distinct_and_stable(setup):
    submission, edition, actor = setup
    edition.reviewers_per_submission = 2
    edition.save()
    first = assign(submission, reviewer(edition), actor)
    second = assign(submission, reviewer(edition), actor)
    assert {first.pseudonym_rank, second.pseudonym_rank} == {1, 2}
    service.cancel_assignment(first, reason="Indisponible", actor=actor)
    third = assign(submission, reviewer(edition), actor)
    # Le relecteur remplacé garde son rang : le remplaçant en reçoit un nouveau.
    assert third.pseudonym_rank == 3


def test_h11_first_rank_is_drawn_at_random():
    """Sur 40 soumissions, le premier relecteur ne reçoit pas toujours le rang 1."""
    edition = screening_submission().edition
    edition.reviewers_per_submission = 3
    edition.save()
    actor = user_actor(make_member(edition, Role.SC_CHAIR))
    user = reviewer(edition)
    edition.max_reviews_per_reviewer = 100
    edition.save()
    ranks = {assign(screening_submission(edition), user, actor).pseudonym_rank for _ in range(40)}
    assert ranks <= {1, 2, 3} and len(ranks) > 1


# --- Conflits (H8, RG-03) -------------------------------------------------------------------


def test_rg03_author_conflict_is_never_overridable(setup):
    submission, edition, actor = setup
    submitter = submission.submitter
    UserRole.objects.create(
        user=submitter,
        edition=edition,
        role=Role.SC_MEMBER,
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )
    with pytest.raises(RuleViolation) as error:
        assign(submission, submitter, actor, override_reason="Je prends la responsabilité")
    assert error.value.code == ErrorCode.CONFLICT_OF_INTEREST
    assert not ReviewAssignment.objects.exists()
    assert not ConflictOfInterest.objects.exists()


def test_rg03_co_author_detected_by_account_or_by_any_of_their_addresses(setup):
    submission, edition, actor = setup
    by_account = reviewer(edition)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=2,
        user=by_account,
        first_name="A",
        last_name="B",
        email="autre@example.org",
    )
    by_address = reviewer(edition)
    EmailAddress.objects.create(user=by_address, email="Ancienne@Example.org", verified=True)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=3,
        first_name="C",
        last_name="D",
        email="ancienne@example.org",
    )
    for user in (by_account, by_address):
        kinds = [conflict.kind for conflict in blocking_conflicts(submission, user)]
        assert kinds == [ConflictKind.AUTHOR]
        with pytest.raises(RuleViolation):
            assign(submission, user, actor, override_reason="Motif")


def test_h8_same_institution_is_normalized_and_overridable_with_a_reason(setup):
    submission, edition, actor = setup
    assert normalized_institution("Université  de Cocody !") == normalized_institution(
        "universite de cocody"
    )
    colleague = reviewer(edition, institution="UNIVERSITÉ DE COCODY")
    with pytest.raises(RuleViolation) as error:
        assign(submission, colleague, actor)
    assert error.value.code == ErrorCode.CONFLICT_OF_INTEREST
    assert "reviewer" in error.value.fields
    assignment = assign(submission, colleague, actor, override_reason="Départements distincts")
    assert assignment.conflict_override_reason == "Départements distincts"
    row = ConflictOfInterest.objects.get()
    assert (row.kind, row.source, row.overridden_by) == (
        ConflictKind.INSTITUTION,
        ConflictSource.SYSTEM,
        actor.user,
    )
    entry = AuditLog.objects.get(action="review.conflict_overridden")
    assert entry.reason == "Départements distincts"
    assert AuditLog.objects.get(action="review.assigned").after["conflicts_overridden"] == [
        "institution"
    ]
    # Levé : le conflit ne bloque plus une nouvelle affectation (après annulation).
    service.cancel_assignment(assignment, reason="Erreur", actor=actor)
    assert blocking_conflicts(submission, colleague) == []


def test_h8_declared_conflict_cancels_the_assignment_and_blocks(setup):
    submission, edition, actor = setup
    in_status(submission, S.UNDER_REVIEW)
    user = reviewer(edition)
    assignment = assign(submission, user, actor)
    grid = create_grid(edition, name="Grille", actor=COMMAND)
    Review.objects.create(assignment=assignment, grid=grid, status=ReviewStatus.SUBMITTED)
    declare_conflict(submission, user, reason="Directeur de thèse d'un auteur", actor=actor)
    assignment.refresh_from_db()
    # Même envoyée, l'évaluation ne compte plus (RG-03).
    assert assignment.status == AssignmentStatus.CANCELLED
    assert len(emails("review/email/cancelled")) == 1
    assert AuditLog.objects.filter(action="review.conflict_declared").count() == 1
    with pytest.raises(RuleViolation):
        assign(submission, user, actor)
    again = assign(submission, user, actor, override_reason="Conflit ancien, levé")
    assert again.status == AssignmentStatus.ACTIVE
    # Nouvelle déclaration : la levée antérieure est effacée.
    declare_conflict(submission, user, reason="Nouveau lien", actor=actor)
    row = ConflictOfInterest.objects.get(kind=ConflictKind.DECLARED)
    assert row.overridden_at is None and row.reason == "Nouveau lien"


def test_h8_declaration_refusals(setup):
    submission, edition, actor = setup
    with pytest.raises(Invalid):
        declare_conflict(submission, reviewer(edition), reason=" ", actor=actor)
    with pytest.raises(Invalid):
        declare_conflict(
            submission, make_member(edition, Role.OC_MEMBER), reason="Motif", actor=actor
        )


def test_rg03_reviewable_assignments():
    """RG-03 : un relecteur n'évalue que s'il est affecté (affectation active, évaluation
    ouverte) et qu'aucun conflit déclaré n'est en cours."""
    submission = screening_submission()
    edition = submission.edition
    actor = user_actor(make_member(edition, Role.SC_CHAIR))
    user = reviewer(edition)
    assignment = assign(submission, user, actor)
    assert not service.reviewable_assignments(user, edition).exists()  # recevabilité
    in_status(submission, S.UNDER_REVIEW)
    assert list(service.reviewable_assignments(user, edition)) == [assignment]
    # Défense en profondeur : un conflit déclaré écarte l'affectation, même restée active.
    conflict = ConflictOfInterest.objects.create(
        submission=submission,
        reviewer=user,
        kind=ConflictKind.DECLARED,
        source=ConflictSource.REVIEWER,
    )
    assert not service.reviewable_assignments(user, edition).exists()
    conflict.overridden_at = timezone.now()
    conflict.save()
    assert service.reviewable_assignments(user, edition).exists()
    service.cancel_assignment(assignment, reason="Remplacé", actor=actor)
    assert not service.reviewable_assignments(user, edition).exists()
    assert not service.reviewable_assignments(user, screening_submission().edition).exists()


# --- Annulation, échéance (H15) -------------------------------------------------------------


def test_h15_cancellation_rules(setup):
    submission, edition, actor = setup
    in_status(submission, S.UNDER_REVIEW)
    user = reviewer(edition)
    assignment = assign(submission, user, actor)
    with pytest.raises(Invalid):
        service.cancel_assignment(assignment, reason="", actor=actor)
    review = Review.objects.create(
        assignment=assignment,
        grid=create_grid(edition, name="Grille", actor=COMMAND),
        status=ReviewStatus.SUBMITTED,
    )
    with pytest.raises(RuleViolation) as error:
        service.cancel_assignment(assignment, reason="Remplacé", actor=actor)
    assert error.value.code == ErrorCode.INVALID_TRANSITION
    review.status = ReviewStatus.DRAFT
    review.save()
    service.cancel_assignment(assignment, reason="Remplacé", actor=actor)
    assignment.refresh_from_db()
    assert (assignment.status, assignment.reason) == (AssignmentStatus.CANCELLED, "Remplacé")
    assert AuditLog.objects.get(action="review.assignment_cancelled").reason == "Remplacé"
    (mail,) = emails("review/email/cancelled")
    assert "Remplacé" not in mail.body_text  # motif interne au comité
    with pytest.raises(RuleViolation):
        service.cancel_assignment(assignment, reason="Encore", actor=actor)


def test_h15_new_due_date_resets_reminders(setup):
    submission, edition, actor = setup
    assignment = assign(submission, reviewer(edition), actor, due_local=dt.datetime(2099, 1, 1))
    ReviewAssignment.objects.filter(pk=assignment.pk).update(reminders=["j7"])
    service.change_due_date(assignment, due_local=dt.datetime(2099, 2, 1, 12), actor=actor)
    assignment.refresh_from_db()
    assert assignment.reminders == []
    assert assignment.due_at.month == 2
    entry = AuditLog.objects.get(action="review.assignment_updated")
    assert entry.before["due_at"].startswith("2099-01-01")


# --- Candidats et expertises (H6, H7) -------------------------------------------------------


def test_h7_candidates_with_load_expertise_and_conflicts(setup):
    submission, edition, actor = setup
    track = submission.track
    expert = reviewer(edition)
    service.set_expertise(expert, edition, [track], actor=user_actor(expert))
    colleague = reviewer(edition, institution="Université de Cocody")
    sc_chair = actor.user
    make_member(edition, Role.OC_MEMBER)
    assign(submission, expert, actor)
    by_user = {c.user.pk: c for c in service.candidates(submission)}
    assert set(by_user) == {expert.pk, colleague.pk, sc_chair.pk}
    assert by_user[expert.pk].tracks == [track.code]
    assert by_user[expert.pk].load == 1 and by_user[expert.pk].assignment is not None
    (conflict,) = by_user[colleague.pk].conflicts
    assert (conflict.kind, conflict.overridable, conflict.overridden) == (
        ConflictKind.INSTITUTION,
        True,
        False,
    )


def test_candidates_query_count_does_not_grow_with_reviewers(setup):
    submission, edition, _actor = setup
    reviewer(edition)
    with CaptureQueriesContext(connection) as few:
        service.candidates(submission)
    for _ in range(4):
        reviewer(edition, institution="Ailleurs")
    with CaptureQueriesContext(connection) as many:
        assert len(service.candidates(submission)) == 6
    assert len(many) == len(few)


def test_h7_expertise_replace_and_refusals(setup):
    _submission, edition, _actor = setup
    user = reviewer(edition)
    first, second = TrackFactory(edition=edition), TrackFactory(edition=edition)
    service.set_expertise(user, edition, [first, second], actor=user_actor(user))
    service.set_expertise(user, edition, [second], actor=user_actor(user))
    assert list(ReviewerTrack.objects.values_list("track_id", flat=True)) == [second.pk]
    with pytest.raises(Invalid):
        service.set_expertise(user, edition, [TrackFactory()], actor=user_actor(user))
    with pytest.raises(NotAllowed):
        oc = make_member(edition, Role.OC_MEMBER)
        service.set_expertise(oc, edition, [first], actor=user_actor(oc))


# --- Intégrité --------------------------------------------------------------------------------


def test_integrity_of_assignments(setup):
    submission, edition, actor = setup
    assignment = assign(submission, reviewer(edition), actor)
    assert check_assignments() == []
    ReviewAssignment.objects.filter(pk=assignment.pk).update(active_key=None)
    ReviewAssignment.objects.create(
        submission=submission,
        reviewer=submission.submitter,
        assigned_at=timezone.now(),
        active_key=f"{submission.pk}:{submission.submitter_id}",
    )
    problems = check_assignments()
    assert len(problems) == 2
    assert any("auteur" in problem for problem in problems)
    assert "reviews.assignments" in {name for name, _check in integrity_checks()}


def test_author_user_factory_institution_is_not_a_reviewer_conflict_by_default(setup):
    """Garde-fou des fabriques : un relecteur sans institution n'est jamais en conflit."""
    submission, edition, _actor = setup
    assert blocking_conflicts(submission, reviewer(edition)) == []
    assert author_user().profile.institution == "Univ."
