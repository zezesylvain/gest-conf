"""Lot L4, étape L4.4 : décisions (H16), publication (RG-09), vue de l'auteur (RG-10),
liste d'attente, version finale (H18), classement et simulation (US-06), export (RG-17)."""

from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pypdf import PdfWriter

from apps.accounts.models import Profile
from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import Notification, NotificationKind, OutboxEmail
from apps.conferences.models import KeyDateCode
from apps.conferences.tests.factories import KeyDateFactory, SubmissionTypeFactory
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.core.models import AuditLog
from apps.reviews.anonymity import find_identity_leaks
from apps.reviews.models import Decision, DecisionOutcome, FinalVersion, Review
from apps.reviews.services import assignments, decisions
from apps.reviews.services import reviews as services
from apps.reviews.services.grids import create_grid
from apps.reviews.tests.helpers import in_status, screening_submission
from apps.submissions import workflow
from apps.submissions.models import SubmissionAuthor, SubmissionFile, SubmissionFileKind
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import user_actor

pytestmark = pytest.mark.django_db

SCORES = {"originalite": "4", "methode": "4", "pertinence": "3", "redaction": "3", "impact": "3"}
SECRET = "CONFIDENTIEL-COMITE"


def review_data(comment: str, score: str | None = None) -> dict:
    return {
        "scores": dict.fromkeys(SCORES, score) if score else SCORES,
        "recommendation": "accept",
        "confidence": 3,
        "comment_to_authors": comment,
        "comment_to_committee": SECRET,
    }


def reviewed(edition, chair_actor, reviewers, *, scores=("4", "4"), title="Étude"):
    """Soumission évaluée (RG-07) par les relecteurs donnés."""
    submission = screening_submission(edition, title=title)
    rows = [assignments.assign(submission, user, actor=chair_actor) for user in reviewers]
    assignments.screen(submission, admissible=True, reason="", actor=chair_actor)
    for index, (row, user) in enumerate(zip(rows, reviewers, strict=True)):
        services.submit_review(
            row,
            review_data(f"Commentaire {index + 1}", scores[index]),
            actor=user_actor(user),
        )
    submission.refresh_from_db()
    assert submission.status == S.REVIEWED
    return submission


def named_reviewer(edition, first: str, last: str, email: str):
    user = make_member(edition, Role.SC_MEMBER, email=email)
    Profile.objects.update_or_create(
        user=user, defaults={"first_name": first, "last_name": last, "institution": ""}
    )
    return user


@pytest.fixture
def world():
    edition = screening_submission().edition
    edition.reviewers_per_submission = 2
    edition.save()
    chair = make_member(edition, Role.SC_CHAIR)
    actor = user_actor(chair)
    create_grid(edition, name="Grille", actor=actor)
    reviewers = (
        named_reviewer(edition, "Romain", "Rolland", "romain.rolland@trace.example"),
        named_reviewer(edition, "Ruth", "Revue", "ruth.revue@trace.example"),
    )
    submission = reviewed(edition, actor, reviewers)
    return {
        "edition": edition,
        "chair": chair,
        "actor": actor,
        "reviewers": reviewers,
        "submission": submission,
    }


def pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.add_metadata({"/Author": "Kofi Mensah"})
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


# --- Décisions provisoires (H16) -------------------------------------------------------------


def test_h16_provisional_decision_defaults_and_audit(world):
    submission = world["submission"]
    decision = decisions.record_decision(
        submission, outcome=DecisionOutcome.ACCEPTED, actor=world["actor"]
    )
    assert decision.assigned_type == submission.submission_type
    assert decision.published_at is None
    poster = SubmissionTypeFactory(edition=world["edition"], code="poster")
    decision = decisions.record_decision(
        submission,
        outcome=DecisionOutcome.ACCEPTED_MINOR,
        assigned_type="poster",
        comment_to_authors="Raccourcir.",
        actor=world["actor"],
    )
    assert decision.assigned_type == poster
    entries = AuditLog.objects.filter(action="decision.recorded").order_by("id")
    assert entries.count() == 2 and entries.last().before["outcome"] == "accepted"
    with pytest.raises(Invalid):
        decisions.record_decision(
            submission, outcome="accepted", assigned_type="inconnu", actor=world["actor"]
        )
    with pytest.raises(Invalid):
        decisions.record_decision(submission, outcome="peut-etre", actor=world["actor"])


def test_h16_decision_requires_a_reviewed_submission(world):
    pending = in_status(screening_submission(world["edition"]), S.UNDER_REVIEW)
    with pytest.raises(RuleViolation) as error:
        decisions.record_decision(pending, outcome="rejected", actor=world["actor"])
    assert error.value.code == ErrorCode.INVALID_TRANSITION


def test_rg06_reviews_are_frozen_once_a_decision_is_recorded(world):
    """RG-06 : une évaluation envoyée est modifiable jusqu'à la décision."""
    submission = world["submission"]
    first = world["reviewers"][0]
    assignment = submission.assignments.get(reviewer=first)
    decisions.record_decision(submission, outcome="accepted", actor=world["actor"])
    with pytest.raises(RuleViolation) as error:
        services.submit_review(assignment, review_data("Changé"), actor=user_actor(first))
    assert error.value.code == ErrorCode.REVIEW_NOT_OPEN
    decisions.cancel_decision(submission, actor=world["actor"])
    assert not Decision.objects.exists()
    services.submit_review(assignment, review_data("Changé"), actor=user_actor(first))


def test_h16_batch_is_all_or_nothing(world):
    other = in_status(screening_submission(world["edition"]), S.UNDER_REVIEW)
    items = [
        {"submission": world["submission"], "outcome": "accepted"},
        {"submission": other, "outcome": "rejected"},
    ]
    with pytest.raises(Invalid) as error:
        decisions.record_decisions(world["edition"], items, actor=world["actor"])
    assert list(error.value.fields) == ["1"]
    assert other.reference in error.value.fields["1"][0]
    assert not Decision.objects.exists()
    recorded = decisions.record_decisions(world["edition"], items[:1], actor=world["actor"])
    assert len(recorded) == 1


# --- Publication (RG-09) et vue de l'auteur (RG-10) ----------------------------------------


def test_rg09_decision_invisible_to_authors_until_published(world):
    submission = world["submission"]
    decisions.record_decision(
        submission, outcome="accepted", comment_to_authors="Bravo.", actor=world["actor"]
    )
    author = client_for(submission.submitter, mfa=False)
    body = author.get(f"/v1/submissions/{submission.pk}").json()
    assert body["decision"] is None and body["status"] == S.REVIEWED
    assert not OutboxEmail.objects.filter(template_code="submission/email/decision").exists()
    assert decisions.publish_decisions(world["edition"], actor=world["actor"]) == 1
    submission.refresh_from_db()
    assert submission.status == S.ACCEPTED
    body = author.get(f"/v1/submissions/{submission.pk}").json()
    assert body["decision"]["outcome"] == "accepted"
    assert body["decision"]["comment_to_authors"] == "Bravo."
    assert "final_version" in body["allowed_actions"]
    assert AuditLog.objects.get(action="decision.published").after["count"] == 1
    # Rien de plus à publier.
    assert decisions.publish_decisions(world["edition"], actor=world["actor"]) == 0


def test_rg10_authors_never_see_reviewer_identity_scores_or_committee_comments(world):
    """RG-10 : commentaires aux auteurs sous pseudonyme ; ni identité, ni notes, ni
    commentaire confidentiel, dans l'API comme dans l'e-mail."""
    submission = world["submission"]
    SubmissionAuthor.objects.create(
        submission=submission,
        position=2,
        first_name="Adjoua",
        last_name="Traoré",
        email="adjoua@univ.example",
    )
    decisions.record_decision(submission, outcome="rejected", actor=world["actor"])
    decisions.publish_decisions(world["edition"], actor=world["actor"])
    tracers = [
        "Romain",
        "Rolland",
        "romain.rolland@trace.example",
        "Ruth",
        "Revue",
        "ruth.revue@trace.example",
        SECRET,
    ]
    payload = (
        client_for(submission.submitter, mfa=False)
        .get(f"/v1/submissions/{submission.pk}")
        .json()["decision"]
    )
    assert find_identity_leaks(payload, tracers) == []
    assert "scores" not in str(payload) and "weighted_score" not in str(payload)
    assert sorted(item["comment"] for item in payload["reviews"]) == [
        "Commentaire 1",
        "Commentaire 2",
    ]
    assert sorted(item["pseudonym_rank"] for item in payload["reviews"]) == [1, 2]
    mails = OutboxEmail.objects.filter(template_code="submission/email/decision")
    assert sorted(mail.to_email for mail in mails) == sorted(
        [submission.submitter.email, "adjoua@univ.example"]
    )
    for mail in mails:
        assert "Commentaire 1" in mail.body_text
        assert not [t for t in tracers if t in mail.body_text], mail.body_text
    submitter_mail = mails.get(to_email=submission.submitter.email)
    assert f"/compte/soumissions/{submission.pk}" in submitter_mail.body_text
    assert "/compte/soumissions" not in mails.get(to_email="adjoua@univ.example").body_text
    note = Notification.objects.get(user=submission.submitter, kind="decision_published")
    assert note.payload["outcome"] == "rejected"


def test_rg09_publication_capability_is_rechecked_by_the_workflow(world):
    decisions.record_decision(world["submission"], outcome="accepted", actor=world["actor"])
    member = user_actor(world["reviewers"][0])
    with pytest.raises(NotAllowed):
        decisions.publish_decisions(world["edition"], actor=member)
    assert Decision.objects.get().published_at is None


def test_rg09_no_decision_status_without_a_decision(world):
    with pytest.raises(RuleViolation) as error:
        workflow.transition(world["submission"], S.ACCEPTED, world["actor"])
    assert error.value.code == ErrorCode.INVALID_TRANSITION


def test_h16_waitlist_then_promotion(world):
    submission = world["submission"]
    decisions.record_decision(submission, outcome="waitlist", actor=world["actor"])
    decisions.publish_decisions(world["edition"], actor=world["actor"])
    submission.refresh_from_db()
    assert submission.status == S.WAITLIST
    decisions.promote(submission, actor=world["actor"])
    submission.refresh_from_db()
    assert submission.status == S.ACCEPTED
    assert Decision.objects.get().outcome == "accepted"
    assert OutboxEmail.objects.filter(template_code="submission/email/decision").count() == 2
    with pytest.raises(RuleViolation):
        decisions.promote(submission, actor=world["actor"])


def test_publish_api_requires_recent_authentication(world):
    decisions.record_decision(world["submission"], outcome="accepted", actor=world["actor"])
    url = f"/v1/manage/editions/{world['edition'].pk}/decisions/publish"
    stale = client_for(world["chair"], recent_auth=False).post(url)
    assert (stale.status_code, stale.json()["code"]) == (403, "reauthentication_required")
    assert client_for(world["chair"]).post(url).json() == {"published": 1}


# --- Version finale (H18) --------------------------------------------------------------------


def accepted(world, outcome="accepted"):
    submission = world["submission"]
    decisions.record_decision(submission, outcome=outcome, actor=world["actor"])
    decisions.publish_decisions(world["edition"], actor=world["actor"])
    submission.refresh_from_db()
    return submission


def test_h18_final_version_upload_replaces_and_moves_status(world):
    submission = accepted(world)
    client = client_for(submission.submitter, mfa=False)
    url = f"/v1/submissions/{submission.pk}/final-version"
    upload = SimpleUploadedFile("final.txt", b"texte", content_type="text/plain")
    assert client.post(url, {"file": upload}, format="multipart").status_code == 400
    upload = SimpleUploadedFile("final.pdf", pdf(), content_type="application/pdf")
    response = client.post(url, {"file": upload, "response_letter": "Merci."}, format="multipart")
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["status"] == S.CAMERA_READY_RECEIVED
    assert body["final_version"]["file"]["version"] == 1
    stored = SubmissionFile.objects.get(kind=SubmissionFileKind.CAMERA_READY)
    assert stored.metadata_removed is False  # version nominative
    upload = SimpleUploadedFile("final-2.pdf", pdf(), content_type="application/pdf")
    body = client.post(url, {"file": upload}, format="multipart").json()
    assert body["final_version"]["file"]["version"] == 2
    assert FinalVersion.objects.count() == 1
    assert client.get(f"{url}/content").status_code == 200
    assert OutboxEmail.objects.filter(template_code="submission/email/final_received").count() == 2
    assert Notification.objects.filter(kind=NotificationKind.FINAL_VERSION_RECEIVED).count() == 2
    # Gestion : la version finale se télécharge comme le PDF principal.
    manage = client_for(world["chair"]).get(
        f"/v1/manage/editions/{world['edition'].pk}/submissions/{submission.pk}"
        f"/files/{SubmissionFile.objects.get(is_current=True, kind='camera_ready').pk}/content"
    )
    assert manage.status_code == 200 and "-final-v2.pdf" in manage["Content-Disposition"]


def test_h18_rules(world):
    submission = accepted(world, outcome="accepted_minor")
    with pytest.raises(Invalid) as error:
        decisions.submit_final_version(
            submission,
            data=pdf(),
            name="f.pdf",
            response_letter="",
            actor=user_actor(submission.submitter),
        )
    assert "response_letter" in error.value.fields
    with pytest.raises(NotAllowed):
        decisions.submit_final_version(
            submission,
            data=pdf(),
            name="f.pdf",
            response_letter="Lettre",
            actor=world["actor"],
        )
    KeyDateFactory(
        edition=world["edition"],
        code=KeyDateCode.CAMERA_READY,
        at=timezone.now() - dt.timedelta(hours=1),
    )
    with pytest.raises(RuleViolation) as error:
        decisions.submit_final_version(
            submission,
            data=pdf(),
            name="f.pdf",
            response_letter="Lettre",
            actor=user_actor(submission.submitter),
        )
    assert error.value.code == ErrorCode.DEADLINE_PASSED


def test_h18_no_final_version_for_a_rejected_submission(world):
    submission = accepted(world, outcome="rejected")
    with pytest.raises(RuleViolation):
        decisions.submit_final_version(
            submission,
            data=pdf(),
            name="f.pdf",
            response_letter="",
            actor=user_actor(submission.submitter),
        )


def test_withdrawal_after_acceptance_with_a_reason(world):
    submission = accepted(world)
    with pytest.raises(Invalid):
        workflow.transition(submission, S.WITHDRAWN, user_actor(submission.submitter))
    workflow.transition(
        submission, S.WITHDRAWN, user_actor(submission.submitter), reason="Visa refusé"
    )
    submission.refresh_from_db()
    assert submission.status == S.WITHDRAWN


# --- Classement, simulation (US-06), export --------------------------------------------------


def test_us06_ranking_and_threshold_simulation(world):
    edition = world["edition"]
    low = reviewed(edition, world["actor"], world["reviewers"], scores=("1", "2"), title="Basse")
    in_status(screening_submission(edition), S.REJECTED)  # rejet de recevabilité : exclu
    rows = decisions.ranking(edition)
    assert [row.submission.pk for row in rows] == [world["submission"].pk, low.pk]
    assert rows[0].final == Decimal("80.00") and rows[0].recommendations == {"accept": 2}
    simulation = decisions.simulate(rows, Decimal("50"))
    assert (simulation["accepted"], simulation["total"]) == (1, 2)
    url = f"/v1/manage/editions/{edition.pk}/ranking"
    client = client_for(world["chair"])
    body = client.get(f"{url}?threshold=50").json()
    assert body["simulation"]["accepted"] == 1
    assert body["rows"][0]["final_score"] == "80.00"
    assert client.get(url).json()["simulation"] is None
    for bad in ("abc", "150", "NaN"):
        assert client.get(f"{url}?threshold={bad}").status_code == 400


def test_reviews_export_is_nominative_neutralized_and_audited(world):
    edition = world["edition"]
    first = world["reviewers"][0]
    submission = reviewed(edition, world["actor"], world["reviewers"], title="Formule")
    assignment = submission.assignments.get(reviewer=first)
    Review.objects.filter(assignment=assignment).update(comment_to_authors="=HYPERLINK(1)")
    content = decisions.export_reviews_csv(edition, actor=world["actor"])
    lines = content.lstrip("﻿").splitlines()
    assert len(lines) == 5  # en-tête + 2 soumissions x 2 évaluations
    assert "Romain Rolland" in content and SECRET in content
    assert "'=HYPERLINK(1)" in content
    assert lines[0].endswith("impact;methode;originalite;pertinence;redaction")
    assert AuditLog.objects.get(action="review.exported").after == {"count": 4}
