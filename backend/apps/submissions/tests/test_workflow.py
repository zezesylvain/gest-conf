"""Workflow des soumissions (règle n° 4, étude §5.1, plan L3 §2.2) et RG-01, RG-02."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from apps.conferences.models import EditionStatus
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.core.models import AuditLog
from apps.submissions import workflow
from apps.submissions.models import StatusHistory, Submission, SubmissionExtension
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.services import missing_items, word_count
from apps.submissions.tests.factories import (
    author_user,
    complete_submission,
    open_edition,
    user_actor,
)

pytestmark = pytest.mark.django_db

SYSTEM = Actor.system("job:close_call")


def submit(submission, user=None, **kwargs):
    return workflow.transition(
        submission, S.SUBMITTED, user_actor(user or submission.submitter), **kwargs
    )


# --- Table des transitions ------------------------------------------------------------------


def test_table_covers_the_study_diagram():
    """Les 19 transitions de l'étude (§5.1), plus les 3 retraits (I5) et le retour à
    « confirmée » (I6) ajoutés par le plan L5 ; celles des lots L3 à L5 sont disponibles, pas
    les suivantes."""
    assert len(workflow.TRANSITIONS) == 23
    available = {pair for pair, rule in workflow.TRANSITIONS.items() if rule.available}
    assert available == {
        (S.DRAFT, S.SUBMITTED),
        (S.SUBMITTED, S.SCREENING),
        (S.DRAFT, S.WITHDRAWN),
        (S.SUBMITTED, S.WITHDRAWN),
        (S.SCREENING, S.UNDER_REVIEW),
        (S.SCREENING, S.REJECTED),
        (S.UNDER_REVIEW, S.REVIEWED),
        (S.REVIEWED, S.ACCEPTED),
        (S.REVIEWED, S.ACCEPTED_MINOR),
        (S.REVIEWED, S.WAITLIST),
        (S.REVIEWED, S.REJECTED),
        (S.WAITLIST, S.ACCEPTED),
        (S.ACCEPTED, S.CAMERA_READY_RECEIVED),
        (S.ACCEPTED_MINOR, S.CAMERA_READY_RECEIVED),
        (S.ACCEPTED, S.WITHDRAWN),
        # Plan L5 (I5) : confirmation de présentation par l'auteur, retraits.
        (S.CAMERA_READY_RECEIVED, S.CONFIRMED),
        (S.CAMERA_READY_RECEIVED, S.WITHDRAWN),
        (S.CONFIRMED, S.WITHDRAWN),
        (S.SCHEDULED, S.WITHDRAWN),
        # Plan L5 (I6) : à la publication du programme.
        (S.CONFIRMED, S.SCHEDULED),
        (S.SCHEDULED, S.CONFIRMED),
    }
    L5_SOURCES = (S.CAMERA_READY_RECEIVED, S.CONFIRMED, S.SCHEDULED)
    assert all(
        rule.lot == ("L5" if pair[0] in L5_SOURCES else "L4")
        for pair, rule in workflow.TRANSITIONS.items()
        if rule.available
        and pair
        not in {
            (S.DRAFT, S.SUBMITTED),
            (S.SUBMITTED, S.SCREENING),
            (S.DRAFT, S.WITHDRAWN),
            (S.SUBMITTED, S.WITHDRAWN),
        }
    )
    used = {status for pair in workflow.TRANSITIONS for status in pair}
    # REVISION_REQUESTED : aucun arc dans le diagramme de l'étude (écart signalé, L4).
    assert set(S.values) - used == {S.REVISION_REQUESTED}


def test_unavailable_or_illegal_transition_is_refused_and_writes_nothing():
    submission = complete_submission()
    for target in (S.ACCEPTED, S.SCREENING, S.DRAFT):
        with pytest.raises(RuleViolation) as error:
            workflow.transition(submission, target, user_actor(submission.submitter))
        assert error.value.code == ErrorCode.INVALID_TRANSITION
    submission.refresh_from_db()
    assert submission.status == S.DRAFT and submission.revision == 0
    assert not StatusHistory.objects.exists()


def test_status_is_written_only_by_the_workflow():
    """Règle n° 4 : aucun module hors ``workflow.py`` n'écrit le statut d'une soumission."""
    apps_dir = Path(settings.BASE_DIR) / "apps"
    offenders = []
    # Écritures : affectation d'attribut, ou status= passé à update/create (pas filter).
    pattern = re.compile(
        r"\.status\s*=(?!=)|\b(?:update|create|update_or_create|get_or_create)\([^)]*\bstatus\s*="
    )
    # Contre-épreuve : le motif détecte bien les écritures, pas les lectures.
    assert pattern.search("submission.status = S.SUBMITTED")
    assert pattern.search("Submission.objects.filter(pk=1).update(status=S.DRAFT)")
    assert not pattern.search("Submission.objects.filter(status=S.DRAFT)")
    for path in apps_dir.rglob("*.py"):
        relative = path.relative_to(apps_dir).as_posix()
        if "/tests/" in relative or "/migrations/" in relative:
            continue
        if relative == "submissions/workflow.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "Submission" not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and "submission" in line.lower():
                offenders.append(f"{relative}:{number}: {line.strip()}")
    assert offenders == []


# --- Soumission (RG-01, RG-02, F4) ----------------------------------------------------------


def test_rg01_incomplete_submission_is_refused_with_missing_fields():
    submission = complete_submission(title="", keywords=[], declarations={})
    submission.authors.update(is_corresponding=False)
    with pytest.raises(RuleViolation) as error:
        submit(submission)
    assert error.value.code == ErrorCode.SUBMISSION_INCOMPLETE
    assert set(error.value.fields) == {"title", "keywords", "authors", "declarations"}
    assert Submission.objects.get().status == S.DRAFT


def test_rg01_rules_in_detail():
    edition = open_edition()
    submission = complete_submission(edition)
    assert missing_items(submission) == {}
    submission.submission_type.abstract_max_words = 50
    submission.abstract = "mot " * 51
    submission.keywords = [f"k{i}" for i in range(7)]
    submission.language = "de"
    submission.submission_type.file_policy = "required"
    problems = missing_items(submission)
    assert set(problems) == {"abstract", "keywords", "language", "file"}
    assert "51" in problems["abstract"][0]
    submission.track.is_active = False
    assert "track" in missing_items(submission)
    # Le soumissionnaire doit figurer parmi les auteurs (F6).
    submission.authors.update(user=None)
    assert "authors" in missing_items(submission)


def test_word_count_keeps_apostrophes_and_hyphens_inside_words():
    # « L'appel », « bien-être », « aujourd\u2019hui » (apostrophe typographique), « 3 »,
    # « jours ».
    assert word_count("L'appel bien-être, aujourd\u2019hui : 3 jours.") == 5


def test_rg01_submit_assigns_reference_history_and_audit():
    submission = complete_submission()
    code = submission.edition.code
    submitted = submit(submission)
    assert submitted.status == S.SUBMITTED
    assert submitted.reference == f"{code}-0001"
    assert submitted.submitted_at is not None and submitted.revision == 1
    history = StatusHistory.objects.get()
    assert (history.from_status, history.to_status) == (S.DRAFT, S.SUBMITTED)
    assert history.actor == submission.submitter
    entry = AuditLog.objects.get(action="submission.status_changed")
    assert entry.after == {"status": S.SUBMITTED, "reference": f"{code}-0001"}
    second = complete_submission(submission.edition)
    assert submit(second).reference == f"{code}-0002"


def test_f4_failed_submission_consumes_no_number():
    """F4 : un refus dans la transaction n'use aucun numéro (pas de trou)."""
    edition = open_edition()
    incomplete = complete_submission(edition, title="")
    with pytest.raises(RuleViolation):
        submit(incomplete)
    assert submit(complete_submission(edition)).reference.endswith("-0001")


def test_only_the_submitter_submits():
    submission = complete_submission()
    with pytest.raises(NotAllowed):
        submit(submission, user=author_user())
    with pytest.raises(NotAllowed):
        workflow.transition(submission, S.SUBMITTED, SYSTEM)


def test_rg02_closed_call_refuses_submission_unless_extension():
    edition = open_edition(opens_in_days=-20, closes_in_days=-1)
    submission = complete_submission(edition)
    with pytest.raises(RuleViolation) as error:
        submit(submission)
    assert error.value.code == ErrorCode.CALL_CLOSED
    extension = SubmissionExtension.objects.create(
        submission=submission,
        until=timezone.now() + dt.timedelta(hours=48),
        reason="Panne du serveur",
        granted_at=timezone.now(),
    )
    assert submit(submission).status == S.SUBMITTED
    # Dérogation révoquée : plus d'écriture possible.
    extension.revoked_at = timezone.now()
    extension.save()
    other = complete_submission(edition)
    SubmissionExtension.objects.create(
        submission=other,
        until=timezone.now() - dt.timedelta(hours=1),
        reason="Échue",
        granted_at=timezone.now(),
    )
    with pytest.raises(RuleViolation):
        submit(other)


def test_rg02_unpublished_edition_has_no_open_call():
    edition = open_edition()
    edition.status = EditionStatus.DRAFT
    edition.save()
    with pytest.raises(RuleViolation) as error:
        submit(complete_submission(edition))
    assert error.value.code == ErrorCode.CALL_CLOSED


def test_archived_edition_refuses_transitions():
    submission = complete_submission()
    submission.edition.status = EditionStatus.ARCHIVED
    submission.edition.save()
    with pytest.raises(RuleViolation) as error:
        submit(submission)
    assert error.value.code == ErrorCode.EDITION_ARCHIVED


# --- Retrait et clôture -------------------------------------------------------------------


def test_withdrawal_needs_a_reason_once_submitted():
    draft = complete_submission()
    assert workflow.transition(draft, S.WITHDRAWN, user_actor(draft.submitter)).status == (
        S.WITHDRAWN
    )
    submitted = submit(complete_submission())
    with pytest.raises(Invalid):
        workflow.transition(submitted, S.WITHDRAWN, user_actor(submitted.submitter))
    withdrawn = workflow.transition(
        submitted, S.WITHDRAWN, user_actor(submitted.submitter), reason="Conflit de dates"
    )
    assert withdrawn.withdraw_reason == "Conflit de dates" and withdrawn.withdrawn_at
    assert withdrawn.reference  # la référence est conservée
    assert StatusHistory.objects.filter(to_status=S.WITHDRAWN, reason="Conflit de dates").exists()


def test_screening_starts_at_call_close_by_the_system_only():
    edition = open_edition()
    submission = submit(complete_submission(edition))
    with pytest.raises(RuleViolation):  # appel encore ouvert
        workflow.transition(submission, S.SCREENING, SYSTEM)
    closes = edition.key_dates.get(code="call_close").at
    later = closes + dt.timedelta(minutes=1)
    with pytest.raises(NotAllowed):
        workflow.transition(submission, S.SCREENING, user_actor(submission.submitter), now=later)
    SubmissionExtension.objects.create(
        submission=submission,
        until=later + dt.timedelta(hours=1),
        reason="Dérogation",
        granted_at=timezone.now(),
    )
    with pytest.raises(RuleViolation):  # dérogation en cours
        workflow.transition(submission, S.SCREENING, SYSTEM, now=later)
    after = later + dt.timedelta(hours=2)
    assert workflow.transition(submission, S.SCREENING, SYSTEM, now=after).status == S.SCREENING
    assert StatusHistory.objects.filter(to_status=S.SCREENING, actor_label="job:close_call")


def test_effects_run_inside_the_transition():
    """Effets dans la transaction : un effet qui échoue annule la transition."""
    calls = []

    def effect(submission, frm, to, actor):
        calls.append((submission.reference, frm, to))

    workflow.register_effect(effect)
    try:
        submitted = submit(complete_submission())
        assert calls == [(submitted.reference, S.DRAFT, S.SUBMITTED)]
    finally:
        workflow._EFFECTS.remove(effect)

    def failing(submission, frm, to, actor):
        raise RuntimeError("panne")

    workflow.register_effect(failing)
    try:
        draft = complete_submission()
        with pytest.raises(RuntimeError):
            submit(draft)
        draft.refresh_from_db()
        assert draft.status == S.DRAFT and draft.reference is None
    finally:
        workflow._EFFECTS.remove(failing)


def test_allowed_targets():
    submission = complete_submission()
    assert set(workflow.allowed_targets(submission)) == {S.SUBMITTED, S.WITHDRAWN}
