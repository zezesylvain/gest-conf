"""Lot L4, étape L4.2 : API de gestion de la recevabilité et des affectations (plan L4 §4)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.reviews.models import ConflictKind, Review, ReviewAssignment, ReviewStatus
from apps.reviews.services import assignments
from apps.reviews.services.grids import create_grid
from apps.reviews.tests.helpers import in_status, reviewer, screening_submission
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import complete_submission, user_actor

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    submission = screening_submission()
    edition = submission.edition
    chair = make_member(edition, Role.SC_CHAIR)
    return submission, edition, chair


def url(edition, path: str) -> str:
    return f"/v1/manage/editions/{edition.pk}/{path}"


def test_review_submissions_list_counts_and_filters(world):
    submission, edition, chair = world
    edition.reviewers_per_submission = 2
    edition.save()
    actor = user_actor(chair)
    under_review = in_status(screening_submission(edition, title="Deuxième"), S.UNDER_REVIEW)
    late = assignments.assign(
        under_review, reviewer(edition), actor=actor, due_local=dt.datetime(2099, 1, 1)
    )
    ReviewAssignment.objects.filter(pk=late.pk).update(due_at=timezone.now() - dt.timedelta(days=1))
    done = assignments.assign(under_review, reviewer(edition), actor=actor)
    Review.objects.create(
        assignment=done,
        grid=create_grid(edition, name="G", actor=actor),
        status=ReviewStatus.SUBMITTED,
    )
    screening_submission(edition, title="Brouillon")  # en recevabilité, sans relecteur
    complete_submission(edition)  # brouillon : hors du suivi
    client = client_for(chair)
    body = client.get(url(edition, "review-submissions")).json()
    assert body["count"] == 3
    row = next(item for item in body["results"] if item["id"] == under_review.pk)
    assert (row["assignment_count"], row["review_count"], row["late_count"], row["required"]) == (
        2,
        1,
        1,
        2,
    )
    late_only = client.get(url(edition, "review-submissions?late=true")).json()
    assert [item["id"] for item in late_only["results"]] == [under_review.pk]
    missing = client.get(url(edition, "review-submissions?missing=true")).json()
    assert under_review.pk not in [item["id"] for item in missing["results"]]
    assert submission.pk in [item["id"] for item in missing["results"]]
    status = client.get(url(edition, "review-submissions?status=under_review")).json()
    assert [item["id"] for item in status["results"]] == [under_review.pk]
    search = client.get(url(edition, "review-submissions?q=Deuxi")).json()
    assert [item["id"] for item in search["results"]] == [under_review.pk]


def test_detail_lists_assignments_and_conflicts_with_names_never_addresses(world):
    submission, edition, chair = world
    user = reviewer(edition)
    client = client_for(chair)
    response = client.post(
        url(edition, "assignments"),
        {"submission": submission.pk, "reviewer": user.pk},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["reviewer"] == {"id": user.pk, "name": f"Rita Relectrice{user.pk}"}
    other = reviewer(edition)
    response = client.post(
        url(edition, "conflicts"),
        {"submission": submission.pk, "reviewer": other.pk, "reason": "Co-encadrant"},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["kind"] == ConflictKind.DECLARED
    detail = client.get(url(edition, f"review-submissions/{submission.pk}")).json()
    assert [a["reviewer"]["id"] for a in detail["assignments"]] == [user.pk]
    assert detail["assignments"][0]["review_status"] is None
    assert [c["reviewer"]["id"] for c in detail["conflicts"]] == [other.pk]
    assert detail["abstract"] and detail["keywords"] == ["ia"]
    text = str(detail)
    assert user.email not in text and other.email not in text


def test_candidates_endpoint(world):
    submission, edition, chair = world
    colleague = reviewer(edition, institution="Université de Cocody")
    body = client_for(chair).get(url(edition, f"review-submissions/{submission.pk}/candidates"))
    payload = body.json()
    assert payload["max_load"] == edition.max_reviews_per_reviewer
    assert payload["track"] == submission.track.code
    row = next(item for item in payload["candidates"] if item["id"] == colleague.pk)
    assert row["institution"] == "Université de Cocody"
    assert row["conflicts"] == [{"kind": "institution", "overridable": True, "overridden": False}]
    assert row["assignment_id"] is None and row["load"] == 0


def test_conflict_override_requires_recent_authentication(world):
    """Plan L4 §6 : la levée d'un conflit exige une réauthentification récente."""
    submission, edition, chair = world
    colleague = reviewer(edition, institution="Université de Cocody")
    body = {"submission": submission.pk, "reviewer": colleague.pk}
    stale = client_for(chair, recent_auth=False)
    refused = stale.post(url(edition, "assignments"), body, format="json")
    assert (refused.status_code, refused.json()["code"]) == (409, "conflict_of_interest")
    with_reason = {**body, "override_reason": "Départements distincts"}
    response = stale.post(url(edition, "assignments"), with_reason, format="json")
    assert (response.status_code, response.json()["code"]) == (403, "reauthentication_required")
    assert not ReviewAssignment.objects.exists()
    response = client_for(chair).post(url(edition, "assignments"), with_reason, format="json")
    assert response.status_code == 201
    assert response.json()["conflict_override_reason"] == "Départements distincts"


def test_screening_cancel_and_due_date_endpoints(world):
    submission, edition, chair = world
    client = client_for(chair)
    first = client.post(
        url(edition, "assignments"),
        {"submission": submission.pk, "reviewer": reviewer(edition).pk},
        format="json",
    ).json()
    response = client.post(
        url(edition, f"review-submissions/{submission.pk}/screening"),
        {"decision": "admissible"},
        format="json",
    )
    assert (response.status_code, response.json()["code"]) == (409, "reviewers_missing")
    client.post(
        url(edition, "assignments"),
        {"submission": submission.pk, "reviewer": reviewer(edition).pk},
        format="json",
    )
    response = client.post(
        url(edition, f"review-submissions/{submission.pk}/screening"),
        {"decision": "admissible"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["status"] == S.UNDER_REVIEW
    response = client.patch(
        url(edition, f"assignments/{first['id']}"),
        {"due_local": "2099-06-30T18:00"},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["due_at"].startswith("2099-06-30")
    response = client.post(url(edition, f"assignments/{first['id']}/cancel"), {}, format="json")
    assert response.status_code == 400
    response = client.post(
        url(edition, f"assignments/{first['id']}/cancel"), {"reason": "Absent"}, format="json"
    )
    assert response.json()["status"] == "cancelled"


def test_unknown_or_foreign_ids_are_refused(world):
    submission, edition, chair = world
    client = client_for(chair)
    foreign = screening_submission()
    response = client.post(
        url(edition, "assignments"),
        {"submission": foreign.pk, "reviewer": reviewer(edition).pk},
        format="json",
    )
    assert response.status_code == 400 and "submission" in response.json()["fields"]
    response = client.post(
        url(edition, "assignments"),
        {"submission": submission.pk, "reviewer": 999999},
        format="json",
    )
    assert response.status_code == 400 and "reviewer" in response.json()["fields"]
    assert client.get(url(edition, f"review-submissions/{foreign.pk}")).status_code == 404
    other_assignment = assignments.assign(
        foreign,
        reviewer(foreign.edition),
        actor=user_actor(make_member(foreign.edition, Role.SC_CHAIR)),
    )
    response = client.post(
        url(edition, f"assignments/{other_assignment.pk}/cancel"),
        {"reason": "x"},
        format="json",
    )
    assert response.status_code == 404


def test_drafts_and_submitted_are_outside_the_review_follow_up(world):
    _submission, edition, chair = world
    client = client_for(chair)
    draft = complete_submission(edition)
    for path in (f"review-submissions/{draft.pk}", f"review-submissions/{draft.pk}/candidates"):
        assert client.get(url(edition, path)).status_code == 404
    submitted = in_status(complete_submission(edition), S.SUBMITTED)
    assert client.get(url(edition, f"review-submissions/{submitted.pk}")).status_code == 404
