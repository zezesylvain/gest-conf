"""API de l'espace auteur (plan L3 §4) : droits, If-Match, révisions, PDF, e-mails, RG-02."""

from __future__ import annotations

import datetime as dt
import io

import pytest
from allauth.account.models import EmailAddress
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from rest_framework.test import APIClient

from apps.accounts.models import Profile, UserRole
from apps.accounts.roles import Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for
from apps.communications.models import OutboxEmail
from apps.conferences.tests.factories import SubmissionTypeFactory, TrackFactory
from apps.core.actor import Actor
from apps.core.models import AuditLog
from apps.submissions import services, storage
from apps.submissions.models import Submission, SubmissionFile, SubmissionRevision
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import (
    ACCEPTED_DECLARATIONS,
    author_user,
    open_edition,
)

pytestmark = pytest.mark.django_db

BASE = "/v1/submissions"


def pdf_bytes(author: str = "", encrypt: bool = False) -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    if author:
        writer.add_metadata({"/Author": author, "/Title": f"Étude de {author}"})
    if encrypt:
        writer.encrypt("secret")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def setup():
    edition = open_edition()
    user = author_user(email="awa@univ.ci")
    track = TrackFactory(edition=edition)
    oral = SubmissionTypeFactory(edition=edition, file_policy="required")
    return edition, user, client_for(user, mfa=False), track, oral


def create(client, edition) -> dict:
    response = client.post(BASE, {"edition": edition.code}, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def fill(client, body, track, oral) -> dict:
    response = client.patch(
        f"{BASE}/{body['id']}",
        {
            "title": "Une étude",
            "abstract": "Un résumé court.",
            "keywords": ["ia", " IA ", "santé"],
            "language": "fr",
            "track": track.pk,
            "submission_type": oral.pk,
            "declarations": {code: True for code in ACCEPTED_DECLARATIONS},
        },
        format="json",
        HTTP_IF_MATCH=str(body["revision"]),
    )
    assert response.status_code == 200, response.json()
    return response.json()


def upload(client, body, data=None, name="article.pdf"):
    return client.post(
        f"{BASE}/{body['id']}/file",
        {"file": SimpleUploadedFile(name, data or pdf_bytes(), "application/pdf")},
        format="multipart",
        HTTP_IF_MATCH=str(body["revision"]),
    )


# --- Création et droits ---------------------------------------------------------------------


def test_create_draft_requires_complete_profile_and_open_call(setup):
    edition, user, client, *_ = setup
    stranger = VerifiedUserFactory()
    response = client_for(stranger, mfa=False).post(BASE, {"edition": edition.code}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "profile_incomplete"
    body = create(client, edition)
    assert body["status"] == S.DRAFT and body["reference"] is None
    assert body["authors"] == [
        {
            "position": 1,
            "first_name": "Awa",
            "last_name": "Zadi",
            "email": "awa@univ.ci",
            "institution": "Univ.",
            "country": "CI",
            "is_corresponding": True,
            "is_presenter": True,
            "has_account": True,
        }
    ]
    assert body["can_edit"] is True and body["allowed_actions"] == ["submit", "withdraw"]
    # D7 : rôle AUTHOR attribué au premier brouillon, une seule fois.
    create(client, edition)
    assert UserRole.objects.filter(user=user, edition=edition, role=Role.AUTHOR).count() == 1
    assert AuditLog.objects.filter(action="submission.created").count() == 2


def test_closed_call_refuses_new_drafts():
    edition = open_edition(opens_in_days=-20, closes_in_days=-1)
    client = client_for(author_user(), mfa=False)
    response = client.post(BASE, {"edition": edition.code}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "call_closed"


def test_author_sees_only_own_submissions(setup):
    edition, _user, client, *_ = setup
    body = create(client, edition)
    other = client_for(author_user(email="koffi@univ.ci"), mfa=False)
    assert other.get(BASE).json() == []
    for method, suffix in (
        ("get", ""),
        ("patch", ""),
        ("delete", ""),
        ("get", "/check"),
        ("get", "/timeline"),
        ("get", "/file/content"),
        ("post", "/submit"),
    ):
        assert getattr(other, method)(f"{BASE}/{body['id']}{suffix}").status_code == 404
    assert APIClient().get(BASE).status_code == 401


# --- Écriture, If-Match, révisions ----------------------------------------------------------


def test_autosave_with_if_match_and_stale_revision(setup):
    edition, _user, client, track, oral = setup
    body = fill(client, create(client, edition), track, oral)
    assert body["keywords"] == ["ia", "santé"] and body["revision"] == 1
    stale = client.patch(f"{BASE}/{body['id']}", {"title": "x"}, format="json", HTTP_IF_MATCH="0")
    assert stale.status_code == 412 and stale.json()["code"] == "stale_revision"
    other_track = TrackFactory()  # autre édition
    response = client.patch(f"{BASE}/{body['id']}", {"track": other_track.pk}, format="json")
    assert response.status_code == 400 and "track" in response.json()["fields"]
    response = client.patch(f"{BASE}/{body['id']}", {"language": "de"}, format="json")
    assert response.status_code == 400
    assert not SubmissionRevision.objects.exists()  # brouillon : pas de cliché


def test_f3_changes_after_submission_create_revisions(setup):
    edition, _user, client, track, oral = setup
    body = fill(client, create(client, edition), track, oral)
    body = upload(client, body).json()
    body = client.post(f"{BASE}/{body['id']}/submit").json()
    assert body["status"] == S.SUBMITTED and body["reference"].endswith("-0001")
    response = client.patch(
        f"{BASE}/{body['id']}",
        {"title": "Un titre corrigé"},
        format="json",
        HTTP_IF_MATCH=str(body["revision"]),
    )
    assert response.status_code == 200 and response.json()["status"] == S.SUBMITTED
    revision = SubmissionRevision.objects.get()
    assert revision.snapshot["title"] == "Un titre corrigé"
    assert revision.snapshot["authors"][0]["email"] == "awa@univ.ci"
    timeline = client.get(f"{BASE}/{body['id']}/timeline").json()
    assert [entry["to_status"] for entry in timeline["history"]] == [S.SUBMITTED]
    assert [entry["number"] for entry in timeline["revisions"]] == [1]
    # Une soumission envoyée ne se supprime pas : elle se retire.
    assert client.delete(f"{BASE}/{body['id']}").json()["code"] == "submission_locked"


def test_authors_full_list_links_verified_accounts(setup):
    edition, _user, client, *_ = setup
    body = create(client, edition)
    colleague = VerifiedUserFactory(email="koffi@univ.ci")
    EmailAddress.objects.filter(user=colleague).update(verified=True)
    authors = [
        {
            "first_name": "Awa",
            "last_name": "Zadi",
            "email": "AWA@univ.ci",
            "is_corresponding": True,
        },
        {"first_name": "Koffi", "last_name": "Yao", "email": "koffi@univ.ci", "country": "ci"},
    ]
    response = client.put(f"{BASE}/{body['id']}/authors", {"authors": authors}, format="json")
    assert response.status_code == 200
    rows = response.json()["authors"]
    assert [(a["email"], a["has_account"], a["country"]) for a in rows] == [
        ("awa@univ.ci", True, ""),
        ("koffi@univ.ci", True, "CI"),
    ]
    entry = AuditLog.objects.get(action="submission.authors_updated")
    assert entry.after == {"count": 2}  # jamais d'adresse dans le journal
    authors.append(dict(authors[1]))
    response = client.put(f"{BASE}/{body['id']}/authors", {"authors": authors}, format="json")
    assert response.status_code == 400 and "authors.3.email" in response.json()["fields"]


# --- Fichier PDF (F2) -----------------------------------------------------------------------


def test_f2_double_blind_pdf_is_stored_without_metadata(setup):
    edition, _user, client, track, oral = setup
    body = fill(client, create(client, edition), track, oral)
    response = upload(client, body, pdf_bytes(author="Awa Zadi"))
    assert response.status_code == 200, response.json()
    file = response.json()["file"]
    assert file["version"] == 1 and file["pages"] == 1 and file["metadata_removed"] is True
    stored = SubmissionFile.objects.get()
    data = storage.read(stored.storage_name)
    assert b"Awa" not in data and not PdfReader(io.BytesIO(data)).metadata
    content = client.get(f"{BASE}/{body['id']}/file/content")
    assert content.status_code == 200 and content.content == data
    assert content["X-Content-Type-Options"] == "nosniff"
    assert content["Content-Disposition"].startswith("attachment;")
    # Nouvelle version : l'ancienne est conservée, non courante.
    second = upload(client, response.json()).json()["file"]
    assert second["version"] == 2
    assert SubmissionFile.objects.filter(is_current=True).count() == 1
    assert SubmissionFile.objects.count() == 2


def test_open_review_keeps_the_original_pdf(setup):
    edition, _user, client, track, oral = setup
    edition.double_blind = False
    edition.save()
    body = fill(client, create(client, edition), track, oral)
    original = pdf_bytes(author="Awa Zadi")
    assert upload(client, body, original).json()["file"]["metadata_removed"] is False
    assert storage.read(SubmissionFile.objects.get().storage_name) == original


@pytest.mark.parametrize(
    ("data", "name", "fragment"),
    [
        (b"<html>pas un pdf</html>", "a.pdf", "n'est pas un PDF"),
        (b"%PDF-1.7\nnimporte quoi", "a.pdf", "illisible"),
        (pdf_bytes(encrypt=True), "a.pdf", "mot de passe"),
        (pdf_bytes(), "a.docx", ".pdf"),
    ],
)
def test_bad_files_are_refused(setup, data, name, fragment):
    edition, _user, client, track, oral = setup
    body = fill(client, create(client, edition), track, oral)
    response = upload(client, body, data, name)
    assert response.status_code == 400
    assert fragment in response.json()["fields"]["file"][0]
    assert not SubmissionFile.objects.exists()


def test_file_policy_and_size_limit(setup):
    edition, _user, client, _track, _oral = setup
    poster = SubmissionTypeFactory(edition=edition, file_policy="none")
    body = create(client, edition)
    body = client.patch(
        f"{BASE}/{body['id']}", {"submission_type": poster.pk}, format="json"
    ).json()
    assert upload(client, body).status_code == 400
    small = SubmissionTypeFactory(edition=edition, file_policy="optional", max_file_mb=1)
    body = client.patch(f"{BASE}/{body['id']}", {"submission_type": small.pk}, format="json").json()
    big = pdf_bytes() + b"%" + b"0" * (1024 * 1024)
    response = upload(client, body, big)
    assert response.status_code == 400 and "1 Mo" in response.json()["fields"]["file"][0]


# --- Soumission, e-mails, retrait -----------------------------------------------------------


def test_check_then_submit_queues_receipt_and_coauthor_emails(setup):
    edition, _user, client, track, oral = setup
    body = create(client, edition)
    check = client.get(f"{BASE}/{body['id']}/check").json()
    # Sans type choisi, le fichier n'est pas encore exigé (F1 : il dépend du type).
    assert check["complete"] is False
    assert {"title", "submission_type", "declarations"} <= set(check["missing"])
    assert "file" not in check["missing"]
    refused = client.post(f"{BASE}/{body['id']}/submit")
    assert refused.status_code == 409 and refused.json()["code"] == "submission_incomplete"
    filled = fill(client, body, track, oral)
    assert "file" in client.get(f"{BASE}/{body['id']}/check").json()["missing"]
    body = upload(client, filled).json()
    client.put(
        f"{BASE}/{body['id']}/authors",
        {
            "authors": [
                {
                    "first_name": "Awa",
                    "last_name": "Zadi",
                    "email": "awa@univ.ci",
                    "is_corresponding": True,
                },
                {"first_name": "Koffi", "last_name": "Yao", "email": "koffi@exemple.org"},
            ]
        },
        format="json",
    )
    assert client.get(f"{BASE}/{body['id']}/check").json() == {"complete": True, "missing": {}}
    body = client.post(f"{BASE}/{body['id']}/submit").json()
    emails = {e.template_code: e for e in OutboxEmail.objects.all()}
    assert set(emails) == {"submission/email/received", "submission/email/coauthor"}
    assert emails["submission/email/received"].to_email == "awa@univ.ci"
    assert body["reference"] in emails["submission/email/received"].body_text
    coauthor = emails["submission/email/coauthor"]
    assert coauthor.to_email == "koffi@exemple.org" and "Awa Zadi" in coauthor.body_text
    assert body["reference"] not in coauthor.subject  # objet sans variable


def test_withdrawal_needs_a_reason_and_notifies(setup):
    edition, _user, client, track, oral = setup
    body = upload(client, fill(client, create(client, edition), track, oral)).json()
    body = client.post(f"{BASE}/{body['id']}/submit").json()
    assert client.post(f"{BASE}/{body['id']}/withdraw", {}, format="json").status_code == 400
    response = client.post(f"{BASE}/{body['id']}/withdraw", {"reason": "Indisponible"})
    assert response.status_code == 200 and response.json()["status"] == S.WITHDRAWN
    assert response.json()["can_edit"] is False and response.json()["allowed_actions"] == []
    assert OutboxEmail.objects.filter(template_code="submission/email/withdrawn").exists()


def test_rg02_writes_refused_after_close_until_extension(setup):
    edition, _user, client, track, oral = setup
    body = upload(client, fill(client, create(client, edition), track, oral)).json()
    body = client.post(f"{BASE}/{body['id']}/submit").json()
    edition.key_dates.filter(code="call_close").update(at=timezone.now() - dt.timedelta(hours=1))
    response = client.patch(f"{BASE}/{body['id']}", {"title": "Trop tard"}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "call_closed"
    assert client.get(f"{BASE}/{body['id']}").json()["can_edit"] is False
    submission = Submission.objects.get()
    until_local = (timezone.now() + dt.timedelta(days=2)).replace(tzinfo=None, microsecond=0)
    extension = services.grant_extension(
        submission, until_local=until_local, reason="Panne réseau", actor=Actor.command("cli:t")
    )
    body = client.get(f"{BASE}/{body['id']}").json()
    assert body["can_edit"] is True
    assert body["deadline"] == extension.until.isoformat().replace("+00:00", "Z")
    response = client.patch(f"{BASE}/{body['id']}", {"title": "Dans le délai"}, format="json")
    assert response.status_code == 200
    assert OutboxEmail.objects.filter(template_code="submission/email/extension").exists()
    assert AuditLog.objects.get(action="submission.extension_granted").reason == "Panne réseau"
    services.revoke_extension(extension, actor=Actor.command("cli:t"))
    assert client.patch(f"{BASE}/{body['id']}", {"title": "x"}, format="json").status_code == 409


def test_draft_deletion_removes_files(setup, django_capture_on_commit_callbacks):
    edition, _user, client, track, oral = setup
    body = upload(client, fill(client, create(client, edition), track, oral)).json()
    path = storage.file_path(SubmissionFile.objects.get().storage_name)
    assert path.exists()
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete(f"{BASE}/{body['id']}").status_code == 204
    assert not Submission.objects.exists() and not path.exists()


def test_profile_change_does_not_alter_submitted_authors(setup):
    """Étude §8.2 : nom et adresse figés dans la soumission."""
    edition, user, client, track, oral = setup
    body = upload(client, fill(client, create(client, edition), track, oral)).json()
    client.post(f"{BASE}/{body['id']}/submit")
    Profile.objects.filter(user=user).update(last_name="Nouveau")
    assert client.get(f"{BASE}/{body['id']}").json()["authors"][0]["last_name"] == "Zadi"
