"""Lot L3, étape L3.5 : doublons (F15), rappels des brouillons et cloche (F13)."""

from __future__ import annotations

import datetime as dt
import importlib

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import Notification, OutboxEmail
from apps.communications.notifications import mark_read, notify, purge_old_notifications
from apps.conferences.models import EditionStatus
from apps.core.actor import Actor
from apps.core.models import CronHeartbeat
from apps.submissions import services, workflow
from apps.submissions.models import DraftReminder, Submission, SubmissionAuthor
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import (
    author_user,
    complete_submission,
    open_edition,
    user_actor,
)

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


def titled(edition, submitter, title, **fields) -> Submission:
    submission = complete_submission(edition, submitter, **fields)
    services.update_submission(submission, {"title": title}, actor=user_actor(submitter))
    submission.refresh_from_db()
    return submission


# --- Doublons (F15) ------------------------------------------------------------------------


def test_normalized_title_ignores_case_accents_punctuation_and_spaces():
    assert services.normalized_title("L'IA,  au service — de la Santé !") == (
        services.normalized_title("l ia au service de la sante")
    )
    assert services.normalized_title("") == ""


def test_migration_copy_of_normalization_matches_the_service():
    """La migration 0003 fige une copie de la normalisation : elle ne doit pas diverger."""
    migration = importlib.import_module("apps.submissions.migrations.0003_duplicates_reminders")
    for title in ("Étude « IA » — 2027 ?", "  Deux   espaces ", "Ça-va_bien"):
        assert migration._title_key(title) == services.normalized_title(title)


def test_f15_duplicate_warning_for_author_is_not_blocking():
    """F15 : même titre normalisé chez le même soumissionnaire → avertissement à la
    vérification ; la soumission reste possible."""
    edition = open_edition()
    user = author_user()
    first = titled(edition, user, "Une étude de cas")
    second = titled(edition, user, "UNE ÉTUDE DE CAS.")
    titled(edition, author_user(), "Une étude de cas")  # autre auteur : pas un doublon
    client = client_for(user, mfa=False)
    body = client.get(f"/v1/submissions/{second.pk}/check").json()
    assert [d["id"] for d in body["duplicates"]] == [first.pk]
    assert body["complete"] is True
    assert client.post(f"/v1/submissions/{second.pk}/submit").status_code == 200


def test_f15_duplicates_flagged_and_filtered_in_management():
    edition = open_edition()
    user = author_user()
    first = titled(edition, user, "Paludisme et climat")
    second = titled(edition, user, "paludisme, et climat")
    withdrawn = titled(edition, user, "Paludisme et climat !")
    workflow.transition(withdrawn, S.WITHDRAWN, user_actor(user))
    alone = titled(edition, user, "Autre sujet")
    chair = client_for(make_member(edition, Role.CHAIR))
    base = f"/v1/manage/editions/{edition.pk}/submissions"
    flags = {row["id"]: row["possible_duplicate"] for row in chair.get(base).json()["results"]}
    assert flags == {first.pk: True, second.pk: True, withdrawn.pk: False, alone.pk: False}
    rows = chair.get(f"{base}?duplicates=true").json()["results"]
    assert {row["id"] for row in rows} == {first.pk, second.pk}


# --- Rappels des brouillons (F13) -------------------------------------------------------------


def test_due_reminder_windows():
    closes = dt.datetime(2027, 3, 31, 23, 59, tzinfo=dt.UTC)
    assert services.due_reminder(closes, closes - dt.timedelta(days=8)) is None
    assert services.due_reminder(closes, closes - dt.timedelta(days=7)) == "j7"
    assert services.due_reminder(closes, closes - dt.timedelta(days=2)) == "j7"
    assert services.due_reminder(closes, closes - dt.timedelta(hours=23)) == "j1"
    assert services.due_reminder(closes, closes) is None


def test_reminders_sent_once_per_draft_and_deadline():
    """F13 : rappel à J-7 puis à J-1, aux brouillons seulement, une seule fois chacun."""
    edition = open_edition(closes_in_days=5)
    draft = complete_submission(edition, author_user(email="draft@u.ci"))
    submitted = complete_submission(edition, author_user(email="done@u.ci"))
    workflow.transition(submitted, S.SUBMITTED, user_actor(submitted.submitter))
    OutboxEmail.objects.all().delete()
    assert services.remind_drafts() == 1
    assert services.remind_drafts() == 0  # idempotente
    reminder = OutboxEmail.objects.get(template_code="submission/email/draft_reminder")
    assert reminder.to_email == "draft@u.ci"
    assert "/compte/soumissions/" in reminder.body_text
    notification = Notification.objects.get(user=draft.submitter)
    assert notification.kind == "draft_reminder"
    assert notification.payload["submission_id"] == draft.pk
    closes = edition.key_dates.get(code="call_close").at
    assert services.remind_drafts(now=closes - dt.timedelta(hours=10)) == 1
    assert services.remind_drafts(now=closes - dt.timedelta(hours=9)) == 0
    assert sorted(DraftReminder.objects.values_list("kind", flat=True)) == ["j1", "j7"]
    assert services.remind_drafts(now=closes + dt.timedelta(minutes=1)) == 0


def test_reminders_skip_unpublished_editions_and_closed_calls():
    archived = open_edition(closes_in_days=3)
    complete_submission(archived)
    archived.status = EditionStatus.ARCHIVED
    archived.save()
    far = open_edition(closes_in_days=30)
    complete_submission(far)
    assert services.remind_drafts() == 0


def test_remind_drafts_command_records_heartbeat():
    complete_submission(open_edition(closes_in_days=2))
    call_command("remind_drafts", verbosity=0)
    assert CronHeartbeat.objects.get(name="remind_drafts").processed_count == 1


# --- Cloche (F13) -----------------------------------------------------------------------------


def test_transitions_and_extension_notify_submitter_and_coauthor_accounts():
    edition = open_edition()
    user = author_user()
    coauthor = author_user(email="co@u.ci")
    submission = complete_submission(edition, user)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=2,
        user=coauthor,
        first_name="Co",
        last_name="Auteur",
        email="co@u.ci",
    )
    workflow.transition(submission, S.SUBMITTED, user_actor(user))
    received = Notification.objects.get(user=user)
    assert received.kind == "submission_received"
    assert received.payload["reference"] == f"{edition.code}-0001"
    coauthored = Notification.objects.get(user=coauthor)
    assert coauthored.kind == "coauthor_added"
    assert "submission_id" not in coauthored.payload  # pas d'accès avant P2 (F5)
    edition.key_dates.filter(code="call_close").update(at=timezone.now() - dt.timedelta(hours=1))
    services.grant_extension(
        submission,
        until_local=(timezone.now() + dt.timedelta(days=2)).replace(tzinfo=None),
        reason="Panne",
        actor=COMMAND,
    )
    workflow.transition(submission, S.WITHDRAWN, user_actor(user), reason="Conflit")
    kinds = list(
        Notification.objects.filter(user=user)
        .order_by("created_at", "id")
        .values_list("kind", flat=True)
    )
    assert kinds == ["submission_received", "extension_granted", "submission_withdrawn"]


def test_notifications_api_lists_own_and_marks_read():
    user = author_user()
    other = author_user(email="autre@u.ci")
    first = notify(user, "submission_received", {"reference": "GC27-0001", "title": "T"})
    second = notify(user, "draft_reminder", {"title": "B"})
    foreign = notify(other, "draft_reminder", {"title": "X"})
    client = client_for(user, mfa=False)
    body = client.get("/v1/me/notifications").json()
    assert body["unread"] == 2
    assert [row["id"] for row in body["results"]] == [second.pk, first.pk]
    response = client.post(
        "/v1/me/notifications/read", {"ids": [first.pk, foreign.pk]}, format="json"
    )
    assert response.json() == {"unread": 1}
    foreign.refresh_from_db()
    assert foreign.read_at is None  # celle d'un autre compte : ignorée
    assert client.post("/v1/me/notifications/read", {}, format="json").json() == {"unread": 0}
    assert APIClient().get("/v1/me/notifications").status_code == 401


def test_notification_for_inactive_or_missing_account_is_skipped():
    user = author_user()
    user.is_active = False
    user.save()
    assert notify(user, "draft_reminder", {}) is None
    assert notify(None, "draft_reminder", {}) is None


def test_notifications_exported_then_deleted_at_anonymization():
    user = author_user()
    notify(user, "draft_reminder", {"title": "Brouillon"})
    exported = export_user_data(user, actor=COMMAND)
    assert exported["notifications"][0]["kind"] == "draft_reminder"
    anonymize_user(user, actor=COMMAND, reason="Demande de la personne")
    assert not Notification.objects.filter(user=user).exists()


def test_old_notifications_purged():
    user = author_user()
    now = timezone.now()
    read_long_ago = notify(user, "draft_reminder", {})
    mark_read(user, [read_long_ago.pk], now=now - dt.timedelta(days=200))
    unread_old = notify(user, "draft_reminder", {})
    Notification.objects.filter(pk=unread_old.pk).update(created_at=now - dt.timedelta(days=400))
    recent = notify(user, "draft_reminder", {})
    assert purge_old_notifications(True, now) == 2
    assert purge_old_notifications(False, now) == 2
    assert list(Notification.objects.values_list("pk", flat=True)) == [recent.pk]
