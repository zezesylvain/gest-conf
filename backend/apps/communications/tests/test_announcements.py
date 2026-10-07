"""Annonces, bandeau, actualités et envois groupés (plan L8, N10 et N11 ; RG-22)."""

from __future__ import annotations

import datetime as dt
import time

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications import announcements as service
from apps.communications import segments
from apps.communications.jobs import send_email
from apps.communications.models import (
    Announcement,
    AnnouncementDelivery,
    AnnouncementOptOut,
    Notification,
    NotificationKind,
    OutboxEmail,
    OutboxStatus,
    SendingStatus,
)
from apps.communications.text import html_to_text
from apps.conferences.models import Conference, EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core import jobs
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, NotAllowed, RuleViolation
from apps.core.jobs import RetryLater
from apps.core.models import AuditLog, Job, JobPriority

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")
ALL = frozenset({"communications.send", "reviews.manage"})
CO = frozenset({"communications.send"})


def as_user(user) -> Actor:
    return Actor(kind=ActorKind.USER, user=user)


@pytest.fixture
def edition():
    edition = EditionFactory(status=EditionStatus.PUBLISHED, timezone="Africa/Abidjan")
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    return edition


def volunteers(edition, count, **fields):
    people = []
    for _index in range(count):
        user = make_member(edition, Role.VOLUNTEER)
        for name, value in fields.items():
            setattr(user, name, value)
        user.save()
        people.append(user)
    return people


def draft(edition, **fields):
    data = {
        "title_fr": "Changement de salle",
        "title_en": "Room change",
        "body_fr": '<p>La plénière a lieu en <a href="/fr/programme/">salle A</a>.</p>',
        "body_en": "<p>The plenary is in room A.</p>",
        "by_email": True,
        "on_bell": True,
        "segment": "volunteers",
        **fields,
    }
    return service.create_announcement(edition, data, capabilities=ALL, actor=COMMAND)


def fan_out_all(announcement):
    while service.fan_out_batch(announcement.pk):
        pass
    announcement.refresh_from_db()
    return announcement


# --- Saisie et canaux ---------------------------------------------------------------------


def test_n10_body_is_sanitized_and_channels_are_checked_at_publication(edition):
    announcement = draft(
        edition,
        body_fr='<p onclick="x()">Bonjour<script>alert(1)</script></p>',
        by_email=False,
        on_bell=False,
        segment="",
    )
    assert announcement.body_fr == "<p>Bonjour</p>"
    with pytest.raises(Invalid) as error:
        service.publish(announcement, capabilities=ALL, actor=COMMAND)
    assert "channels" in error.value.fields
    service.update_announcement(announcement, {"on_bell": True}, capabilities=ALL, actor=COMMAND)
    with pytest.raises(Invalid) as error:
        service.publish(announcement, capabilities=ALL, actor=COMMAND)
    assert "segment" in error.value.fields
    with pytest.raises(Invalid):
        draft(edition, segment="inconnu")


def test_n10_text_version_keeps_links_lists_and_paragraphs():
    """Bilan de L8.0 : ``strip_tags`` perdait la cible des liens et collait les puces."""
    html = (
        '<h3>Accès</h3><p>Voir <a href="/fr/acces/">le plan</a>.<br>Merci.</p>'
        "<ul><li>Bus</li><li>Taxi</li></ul><ol><li>Un</li><li>Deux</li></ol>"
        "<blockquote><p>Citation</p></blockquote>"
    )
    assert html_to_text(html, base_url="https://conf.org") == (
        "Accès\n\nVoir le plan (https://conf.org/fr/acces/).\nMerci.\n\n"
        "- Bus\n- Taxi\n\n1. Un\n2. Deux\n\n> Citation"
    )


# --- RG-22 : envois groupés ---------------------------------------------------------------


def test_rg22_one_email_per_person_in_their_language_with_reason_and_unsubscribe_link(edition):
    """RG-22 : un e-mail par personne (jamais de liste en copie), langue du compte, raison de
    l'envoi et lien de désabonnement ; désabonné : cloche seulement ; journal de masse."""
    french, english, opted_out = volunteers(edition, 3)
    english.locale = "en"
    english.save()
    AnnouncementOptOut.objects.create(user=opted_out, edition=edition)
    announcement = draft(edition)
    assert service.audience(announcement) == {
        "recipients": 3,
        "opted_out": 1,
        "emails": 2,
        "estimated_hours": 1,
    }
    service.publish(announcement, capabilities=ALL, actor=COMMAND)
    announcement = fan_out_all(announcement)
    assert (announcement.recipients_count, announcement.delivered_count) == (3, 3)
    assert announcement.sending_status == SendingStatus.QUEUED
    emails = {email.to_user_id: email for email in OutboxEmail.objects.filter(is_bulk=True)}
    assert set(emails) == {french.pk, english.pk}
    assert all(email.to_email for email in emails.values())
    assert "Changement de salle" in emails[french.pk].body_text
    assert "Room change" in emails[english.pk].body_text
    assert "/desabonnement/" in emails[french.pk].body_text
    assert "Bénévoles" in emails[french.pk].body_text  # raison de l'envoi
    # Lien interne rendu absolu dans les deux versions.
    assert 'href="http' in emails[french.pk].body_html
    assert (
        Job.objects.filter(kind="communications.send_email", priority=JobPriority.BULK).count() == 2
    )
    assert Notification.objects.filter(kind=NotificationKind.ANNOUNCEMENT).count() == 3
    jobs.run_pending(deadline=time.monotonic() + 30)
    assert all(len(message.to) == 1 for message in mail.outbox)
    assert not any(message.cc or message.bcc for message in mail.outbox)
    entry = AuditLog.objects.get(action="announcement.sent")
    assert entry.after == {"segment": "volunteers", "recipients": 3, "bell": True, "email": True}


def test_rg22_fan_out_runs_in_idempotent_batches_and_staggers_half_the_hourly_cap(
    edition, settings, monkeypatch
):
    """Bilan de L8.0 : mise en file par lots ; étalement d'un lot égal à la moitié du
    plafond horaire par heure."""
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 4
    monkeypatch.setattr(service, "FAN_OUT_BATCH", 2)
    volunteers(edition, 5)
    announcement = service.publish(draft(edition, on_bell=False), capabilities=ALL, actor=COMMAND)
    assert Job.objects.filter(kind=service.FAN_OUT_JOB).count() == 1
    assert service.fan_out_batch(announcement.pk) is True
    assert Job.objects.filter(kind=service.FAN_OUT_JOB).count() == 2  # lot suivant en file
    announcement = fan_out_all(announcement)
    assert service.fan_out_batch(announcement.pk) is False  # terminé : sans effet
    assert AnnouncementDelivery.objects.filter(announcement=announcement).count() == 5
    start = announcement.sending_started_at
    hours = sorted(
        round((email.scheduled_at - start).total_seconds() / 3600)
        for email in OutboxEmail.objects.filter(is_bulk=True)
    )
    assert hours == [0, 0, 1, 1, 2]
    assert service.sending_stats(announcement)["remaining_hours"] == 3


def test_rg22_bulk_emails_use_at_most_half_of_the_hourly_cap(edition, settings):
    settings.GESTCONF_EMAIL_MAX_PER_HOUR = 4
    now = timezone.now()
    for index in range(2):
        OutboxEmail.objects.create(
            to_email=f"sent{index}@example.org",
            template_code="communications/email/test",
            locale="fr",
            subject="x",
            status=OutboxStatus.SENT,
            sent_at=now,
            scheduled_at=now,
            is_bulk=True,
        )
    from apps.communications.services import queue_email

    bulk = queue_email(
        template_code="communications/email/test", to_email="a@example.org", bulk=True
    )
    with pytest.raises(RetryLater):
        send_email(Job(payload={"outbox_id": bulk.pk}))
    # Un e-mail de service passe : la moitié du plafond lui reste.
    service_email = queue_email(template_code="communications/email/test", to_email="b@x.org")
    send_email(Job(payload={"outbox_id": service_email.pk}))
    service_email.refresh_from_db()
    assert service_email.status == OutboxStatus.SENT


def test_rg22_cancel_stops_what_has_not_left_and_withdrawal_too(edition):
    volunteers(edition, 3)
    announcement = fan_out_all(service.publish(draft(edition), capabilities=ALL, actor=COMMAND))
    first = OutboxEmail.objects.filter(is_bulk=True).order_by("pk").first()
    send_email(Job(payload={"outbox_id": first.pk}))
    assert service.cancel_sending(announcement, actor=COMMAND) == 2
    statuses = sorted(OutboxEmail.objects.filter(is_bulk=True).values_list("status", flat=True))
    assert statuses == [OutboxStatus.CANCELLED, OutboxStatus.CANCELLED, OutboxStatus.SENT]
    with pytest.raises(RuleViolation):
        service.cancel_sending(announcement, actor=COMMAND)
    announcement.refresh_from_db()
    assert announcement.sending_status == SendingStatus.CANCELLED
    # Une fois publiée, l'annonce garde ses destinataires.
    with pytest.raises(Invalid):
        service.update_announcement(
            announcement, {"segment": "committees.organising"}, capabilities=ALL, actor=COMMAND
        )
    service.withdraw(announcement, actor=COMMAND)
    with pytest.raises(RuleViolation):
        service.withdraw(announcement, actor=COMMAND)


def test_rg22_late_reviewers_segment_is_reserved_to_reviews_manage(edition):
    communication = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.COMMUNICATION)
    client = client_for(communication)
    base = f"/v1/manage/editions/{edition.pk}"
    codes = [row["code"] for row in client.get(f"{base}/segments").json()]
    assert "reviewers.late" not in codes and "volunteers" in codes
    response = client.post(
        f"{base}/announcements",
        {"title_fr": "Relance", "segment": "reviewers.late", "by_email": True},
        format="json",
    )
    assert response.status_code == 403
    with pytest.raises(NotAllowed):
        segments.get_segment("reviewers.late", CO)


def test_rg22_publication_requires_recent_authentication_and_test_goes_to_requester(edition):
    communication = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.COMMUNICATION)
    volunteers(edition, 2)
    announcement = draft(edition)
    base = f"/v1/manage/editions/{edition.pk}/announcements/{announcement.pk}"
    stale = client_for(communication, recent_auth=False)
    response = stale.post(f"{base}/publish")
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"
    client = client_for(communication)
    preview = client.get(f"{base}/preview?locale=en").json()
    assert (preview["recipients"], preview["emails"]) == (2, 2)
    assert "Room change" in preview["body_text"]
    assert client.post(f"{base}/test").status_code == 202
    test = OutboxEmail.objects.get(to_user=communication)
    assert not test.is_bulk and "Essai" in test.body_text
    body = client.post(f"{base}/publish").json()
    assert body["status"] == "published" and body["sending"]["recipients"] == 2
    assert client.post(f"{base}/publish").status_code == 409


# --- N10 : bandeau et actualités ----------------------------------------------------------


def test_n10_banner_is_public_at_once_minimal_and_one_at_a_time(edition):
    now = timezone.localtime(timezone.now(), timezone=dt.UTC).replace(tzinfo=None)
    window = {
        "on_banner": True,
        "on_bell": False,
        "by_email": False,
        "segment": "",
        "banner_message_fr": "Plénière en salle A",
        "banner_starts_local": now - dt.timedelta(hours=1),
        "banner_ends_local": now + dt.timedelta(hours=2),
    }
    first = service.publish(draft(edition, **window), capabilities=ALL, actor=COMMAND)
    response = APIClient().get("/v1/public/portal/banner")
    assert response["Cache-Control"] == "public, max-age=60"
    assert response.json() == {
        "banner": {
            "id": first.pk,
            "title_fr": "Changement de salle",
            "title_en": "Room change",
            "message_fr": "Plénière en salle A",
            "message_en": "",
            "news": False,
        }
    }
    second = draft(edition, **window)
    with pytest.raises(RuleViolation) as error:
        service.publish(second, capabilities=ALL, actor=COMMAND)
    assert error.value.code == "banner_overlap"
    service.withdraw(first, actor=COMMAND)
    assert APIClient().get("/v1/public/portal/banner").json() == {"banner": None}


def test_n10_news_are_public_after_publication_and_count_as_portal_changes(edition):
    from apps.portal.services import pending_changes

    news = draft(edition, on_news=True, on_bell=False, by_email=False, segment="")
    bell_only = draft(edition, title_fr="Cloche seule")
    assert APIClient().get("/v1/public/news").json() == []
    before = pending_changes(edition).count()
    service.publish(news, capabilities=ALL, actor=COMMAND)
    service.publish(bell_only, capabilities=ALL, actor=COMMAND)
    body = APIClient().get("/v1/public/news").json()
    assert [item["title_fr"] for item in body] == ["Changement de salle"]
    assert set(body[0]) == {"id", "title_fr", "title_en", "body_fr", "body_en", "published_at"}
    assert pending_changes(edition).count() == before + 1  # l'actualité seulement


# --- N11 : désabonnement ------------------------------------------------------------------


def test_n11_unsubscribe_link_and_account_preference(edition):
    (person,) = volunteers(edition, 1)
    token = service.unsubscribe_token(person, edition)
    client = APIClient()
    response = client.post("/v1/public/announcements/unsubscribe", {"token": token}, format="json")
    assert response.status_code == 200
    assert response.json()["edition_title_fr"] == edition.title_fr
    assert not service.is_subscribed(person, edition)
    # Rejouer le lien est sans effet ; un jeton altéré est refusé.
    client.post("/v1/public/announcements/unsubscribe", {"token": token}, format="json")
    assert AnnouncementOptOut.objects.filter(user=person).count() == 1
    bad = client.post("/v1/public/announcements/unsubscribe", {"token": token + "x"}, format="json")
    assert bad.status_code == 400
    assert bad.json()["code"] == "unsubscribe_link_invalid"
    mine = client_for(person)
    url = f"/v1/me/editions/{edition.pk}/announcements"
    assert mine.get(url).json() == {"subscribed": False}
    assert mine.put(url, {"subscribed": True}, format="json").json() == {"subscribed": True}
    assert service.is_subscribed(person, edition)
    actions = list(
        AuditLog.objects.filter(action__startswith="announcement.")
        .order_by("at", "id")
        .values_list("action", flat=True)
    )
    assert actions == ["announcement.unsubscribed", "announcement.resubscribed"]


# --- N11 : segments déclarés par les applications -----------------------------------------


def test_n11_segments_are_declared_by_the_applications():
    codes = {segment.code for segment in segments.all_segments()}
    assert {
        "authors.submitted",
        "authors.accepted",
        "program.presenters",
        "program.session_chairs",
        "reviewers.all",
        "reviewers.late",
        "registrations.confirmed",
        "registrations.pending",
        "attendees.present",
        "speakers.invited",
        "committees.scientific",
        "committees.organising",
        "volunteers",
    } <= codes
    reserved = {s.code for s in segments.all_segments() if s.capability}
    assert reserved == {"reviewers.late"}


def test_n11_author_segments_follow_published_statuses(edition):
    from apps.submissions.models import SubmissionAuthor, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    submitted = complete_submission(edition, status=SubmissionStatus.SUBMITTED)
    coauthor = author_user("Koffi", "Yao")
    SubmissionAuthor.objects.create(
        submission=submitted,
        position=2,
        user=coauthor,
        first_name="Koffi",
        last_name="Yao",
        email=coauthor.email,
    )
    accepted = complete_submission(edition, status=SubmissionStatus.ACCEPTED)
    complete_submission(edition)  # brouillon : hors segment
    by_code = {segment.code: segment for segment in segments.all_segments()}
    authors = set(segments.recipients(edition, by_code["authors.submitted"]))
    assert authors == {submitted.submitter, coauthor, accepted.submitter}
    assert set(segments.recipients(edition, by_code["authors.accepted"])) == {accepted.submitter}
    assert not segments.recipients(edition, by_code["program.presenters"]).exists()


def test_n11_registration_segments(edition):
    from apps.registrations.models import RegistrationStatus
    from apps.registrations.tests.factories import make_registration

    paid, waiting = VerifiedUserFactory(), VerifiedUserFactory()
    make_registration(edition, paid, status=RegistrationStatus.CONFIRMED)
    make_registration(edition, waiting, status=RegistrationStatus.PENDING)
    by_code = {segment.code: segment for segment in segments.all_segments()}
    assert list(segments.recipients(edition, by_code["registrations.confirmed"])) == [paid]
    assert list(segments.recipients(edition, by_code["registrations.pending"])) == [waiting]


def test_n11_delivered_announcements_are_in_the_personal_data_export(edition):
    from apps.core.personal_data import export_sections

    (person,) = volunteers(edition, 1)
    fan_out_all(service.publish(draft(edition), capabilities=ALL, actor=COMMAND))
    AnnouncementOptOut.objects.create(user=person, edition=edition)
    data = export_sections(person)
    assert data["announcements_received"][0]["title"] == "Changement de salle"
    assert [row["edition"] for row in data["announcement_opt_outs"]] == [edition.code]
    assert Announcement.objects.count() == 1


def test_n11_late_reviewers_and_present_attendees_segments(edition):
    from apps.events.tests.certificate_helpers import present
    from apps.reviews.models import ReviewAssignment
    from apps.reviews.tests.helpers import in_status, reviewer
    from apps.submissions.models import SubmissionStatus
    from apps.submissions.tests.factories import complete_submission

    submission = in_status(complete_submission(edition), SubmissionStatus.UNDER_REVIEW)
    now = timezone.now()
    late, on_time = reviewer(edition), reviewer(edition)
    for person, due in ((late, now - dt.timedelta(days=1)), (on_time, now + dt.timedelta(days=5))):
        ReviewAssignment.objects.create(
            submission=submission,
            reviewer=person,
            assigned_at=now - dt.timedelta(days=10),
            due_at=due,
            active_key=f"{submission.pk}:{person.pk}",
        )
    by_code = {segment.code: segment for segment in segments.all_segments()}
    assert set(segments.recipients(edition, by_code["reviewers.all"])) == {late, on_time}
    assert list(segments.recipients(edition, by_code["reviewers.late"])) == [late]
    registration = present(edition)
    assert list(segments.recipients(edition, by_code["attendees.present"])) == [registration.user]


def test_n11_program_segments_read_the_published_programme_never_the_draft():
    from apps.accounts.tests.roles_helpers import make_member as member
    from apps.program.services import planning
    from apps.program.services.publication import publish_program
    from apps.program.tests.helpers import COMMAND as PLANNER
    from apps.program.tests.helpers import confirmed, local, session
    from apps.program.tests.helpers import edition as program_edition
    from apps.submissions.tests.factories import user_actor

    current = program_edition()
    chair = member(current, Role.CHAIR)
    morning = session(current, local(1, 9), local(1, 10), title="Santé")
    paper = confirmed(current, duration=20)
    planning.place_submission(morning, paper, actor=PLANNER)
    session_chair = member(current, Role.SESSION_CHAIR)
    planning.add_session_role(morning, session_chair, "chair", actor=PLANNER)
    by_code = {segment.code: segment for segment in segments.all_segments()}
    presenters = by_code["program.presenters"]
    chairs = by_code["program.session_chairs"]
    assert not segments.recipients(current, presenters).exists()  # brouillon seul
    publish_program(current, actor=user_actor(chair))
    assert list(segments.recipients(current, presenters)) == [paper.submitter]
    assert list(segments.recipients(current, chairs)) == [session_chair]
