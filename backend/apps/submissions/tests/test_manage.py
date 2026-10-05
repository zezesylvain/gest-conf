"""Soumissions dans la gestion (plan L3 §4, F8, F10) et clôture de l'appel (§2.2).

Les droits par profil sont dans la matrice (``tests/test_matrix.py``) ; ici : contenu des
réponses, filtres, export (RG-17, injection de formules), dérogations (RG-02) et clôture.
"""

from __future__ import annotations

import csv
import datetime as dt
import io

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import SubmissionTypeFactory, TrackFactory
from apps.core.actor import Actor
from apps.core.models import AuditLog, CronHeartbeat
from apps.submissions import services, storage, workflow
from apps.submissions.models import (
    StatusHistory,
    Submission,
    SubmissionAuthor,
    SubmissionExtension,
    SubmissionFile,
)
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import (
    author_user,
    complete_submission,
    open_edition,
    user_actor,
)

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%%EOF\n"


def submit(submission: Submission) -> Submission:
    workflow.transition(submission, S.SUBMITTED, user_actor(submission.submitter))
    submission.refresh_from_db()
    return submission


def add_author(submission, position, first, last, email, *, corresponding=False):
    return SubmissionAuthor.objects.create(
        submission=submission,
        position=position,
        first_name=first,
        last_name=last,
        email=email,
        institution="INP-HB",
        country="CI",
        is_corresponding=corresponding,
    )


def add_file(submission, version=1, *, current=True):
    name, digest = storage.write(PDF + str(version).encode())
    return SubmissionFile.objects.create(
        submission=submission,
        kind="main",
        version=version,
        storage_name=name,
        original_name=f"article-v{version}.pdf",
        size=len(PDF),
        sha256=digest,
        pages=3,
        is_current=current,
        uploaded_by=submission.submitter,
    )


@pytest.fixture
def world():
    edition = open_edition()
    ai = TrackFactory(edition=edition, code="ia")
    health = TrackFactory(edition=edition, code="sante")
    oral = SubmissionTypeFactory(edition=edition, code="oral", file_policy="none")
    first = submit(
        complete_submission(
            edition,
            author_user("Awa", "Koné", email="awa@univ.ci"),
            title="Apprentissage profond",
            track=ai,
            submission_type=oral,
        )
    )
    add_author(first, 2, "Mariam", "Traoré", "mariam@inp.ci")
    add_file(first, 1, current=False)
    add_file(first, 2)
    second = submit(
        complete_submission(
            edition,
            author_user("Yao", "Kouassi", email="yao@univ.ci"),
            title="Paludisme et climat",
            language="en",
            track=health,
            submission_type=oral,
        )
    )
    draft = complete_submission(
        edition, author_user("Ali", "Diop"), title="Brouillon", track=ai, submission_type=oral
    )
    chair = make_member(edition, Role.CHAIR)
    return {
        "edition": edition,
        "first": first,
        "second": second,
        "draft": draft,
        "chair": client_for(chair),
        "chair_user": chair,
        "base": f"/v1/manage/editions/{edition.pk}/submissions",
    }


# --- Liste et filtres ---------------------------------------------------------------------


def test_list_all_statuses_ordered_by_reference_with_drafts_last(world):
    body = world["chair"].get(world["base"]).json()
    assert body["count"] == 3
    rows = body["results"]
    assert [row["reference"] for row in rows] == [
        world["first"].reference,
        world["second"].reference,
        None,
    ]
    first = rows[0]
    assert first["authors_label"] == "Awa Koné ; Mariam Traoré"
    assert first["authors_count"] == 2
    assert first["pages"] == 3
    assert first["track"] == "ia" and first["submission_type"] == "oral"
    assert "email" not in str(first)  # liste sans adresse


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("status=submitted", {"first", "second"}),
        ("status=draft&status=submitted", {"first", "second", "draft"}),
        ("track=sante", {"second"}),
        ("language=en", {"second"}),
        ("submission_type=oral&status=draft", {"draft"}),
        ("q=traor", {"first"}),  # nom d'un co-auteur
        ("q=paludisme", {"second"}),  # titre
        ("q=-0002", {"second"}),  # référence
    ],
)
def test_list_filters(world, query, expected):
    rows = world["chair"].get(f"{world['base']}?{query}").json()["results"]
    by_id = {world[key].pk: key for key in ("first", "second", "draft")}
    assert {by_id[row["id"]] for row in rows} == expected


def test_list_ordering_and_pagination(world):
    rows = world["chair"].get(f"{world['base']}?ordering=title&page_size=2").json()
    assert [row["title"] for row in rows["results"]] == ["Apprentissage profond", "Brouillon"]
    assert rows["next"]
    assert world["chair"].get(f"{world['base']}?ordering=nimporte").status_code == 400


def test_list_has_no_n_plus_one(world, django_assert_max_num_queries):
    for index in range(5):
        submission = complete_submission(world["edition"], author_user(email=f"x{index}@u.ci"))
        add_author(submission, 2, "Co", f"Auteur{index}", f"co{index}@u.ci")
        add_file(submission)
    with django_assert_max_num_queries(16):
        assert world["chair"].get(world["base"]).status_code == 200


def test_other_edition_submissions_are_invisible(world):
    other = complete_submission()
    assert other.pk not in [r["id"] for r in world["chair"].get(world["base"]).json()["results"]]
    assert world["chair"].get(f"{world['base']}/{other.pk}").status_code == 404


# --- Détail, fichier ----------------------------------------------------------------------


def test_detail_shows_authors_with_emails_files_history(world):
    body = world["chair"].get(f"{world['base']}/{world['first'].pk}").json()
    assert [a["email"] for a in body["authors"]] == ["awa@univ.ci", "mariam@inp.ci"]
    assert [f["version"] for f in body["files"]] == [2, 1]
    assert body["history"][0]["to_status"] == "submitted"
    assert body["history"][0]["actor_name"] == "Awa Koné"
    assert body["submitter_name"] == "Awa Koné"
    assert body["can_extend"] is True
    assert body["extensions"] == []
    assert all(d["accepted"] for d in body["declarations"])


def test_file_versions_downloadable_and_scoped(world):
    files = SubmissionFile.objects.filter(submission=world["first"]).order_by("version")
    response = world["chair"].get(
        f"{world['base']}/{world['first'].pk}/files/{files[0].pk}/content"
    )
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].endswith(f'{world["first"].reference}-v1.pdf"')
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response.content == PDF + b"1"
    # Fichier d'une autre soumission : 404.
    path = f"{world['base']}/{world['second'].pk}/files/{files[0].pk}/content"
    assert world["chair"].get(path).status_code == 404


def test_stats_counts_by_status(world):
    body = world["chair"].get(f"{world['base']}/stats").json()
    assert body["by_status"]["submitted"] == 2
    assert body["by_status"]["draft"] == 1
    assert body["by_status"]["screening"] == 0
    assert (body["total"], body["drafts"]) == (2, 1)


# --- Export (RG-17) ----------------------------------------------------------------------


def test_export_csv_filtered_audited_and_formula_safe(world):
    """RG-17 : l'export de masse est journalisé ; une cellule qui commence par « = », « + »,
    « - » ou « @ » est neutralisée (injection de formules dans un tableur)."""
    Submission.objects.filter(pk=world["second"].pk).update(title='=HYPERLINK("http://x")')
    response = world["chair"].get(f"{world['base']}/export?status=submitted")
    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"].startswith('attachment; filename="soumissions-')
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text[1:]), delimiter=";"))
    assert len(rows) == 3  # en-tête et deux soumissions (brouillon filtré)
    by_reference = {row[0]: row for row in rows[1:]}
    assert by_reference[world["second"].reference][2] == '\'=HYPERLINK("http://x")'
    first = by_reference[world["first"].reference]
    assert first[1] == "Soumise"
    assert "Awa Koné (INP-HB, CI)" not in first[6]  # le soumissionnaire n'a pas d'institution ici
    assert "Mariam Traoré (INP-HB, CI)" in first[6]
    assert first[7] == "awa@univ.ci"  # correspondants seulement
    entry = AuditLog.objects.get(action="submission.exported")
    assert entry.after == {"count": 2, "filters": {"status": ["submitted"]}}
    assert entry.edition_id == world["edition"].pk


@pytest.mark.parametrize("value", ["=1+1", "+1", "-1", "@SUM(A1)", "\tx", "\rx"])
def test_csv_cell_neutralizes_formulas(value):
    assert services.csv_cell(value) == f"'{value}"


def test_csv_cell_keeps_plain_values():
    assert services.csv_cell("Koné") == "Koné"
    assert services.csv_cell(None) == ""
    assert services.csv_cell(3) == "3"


# --- Dérogations (RG-02, F8) ---------------------------------------------------------------


def test_rg02_grant_and_revoke_extension_through_api(world):
    """RG-02 : la gestion accorde une dérogation datée à l'heure de l'édition, motivée,
    journalisée et notifiée ; la révocation la termine."""
    path = f"{world['base']}/{world['first'].pk}/extensions"
    until_local = (timezone.now() + dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    response = world["chair"].post(
        path, {"until_local": until_local, "reason": "Coupure réseau"}, format="json"
    )
    assert response.status_code == 201, response.json()
    extensions = response.json()["extensions"]
    assert len(extensions) == 1 and extensions[0]["is_active"] is True
    assert extensions[0]["granted_by_name"]
    assert OutboxEmail.objects.filter(template_code="submission/email/extension").exists()
    assert AuditLog.objects.get(action="submission.extension_granted").reason == "Coupure réseau"
    rows = world["chair"].get(world["base"]).json()["results"]
    assert next(r for r in rows if r["id"] == world["first"].pk)["extension_until"]

    revoke = f"{path}/{extensions[0]['id']}/revoke"
    body = world["chair"].post(revoke).json()
    assert body["extensions"][0]["is_active"] is False
    assert AuditLog.objects.filter(action="submission.extension_revoked").count() == 1
    world["chair"].post(revoke)  # idempotente
    assert AuditLog.objects.filter(action="submission.extension_revoked").count() == 1


def test_rg02_extension_requires_future_deadline_and_reason(world):
    path = f"{world['base']}/{world['first'].pk}/extensions"
    past = (timezone.now() - dt.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    response = world["chair"].post(path, {"until_local": past, "reason": "x"}, format="json")
    assert response.status_code == 400
    assert "until_local" in response.json()["fields"]
    response = world["chair"].post(path, {"until_local": past}, format="json")
    assert response.status_code == 400 and "reason" in response.json()["fields"]


def test_rg02_no_extension_once_in_screening(world):
    world["edition"].key_dates.filter(code="call_close").update(
        at=timezone.now() - dt.timedelta(hours=1)
    )
    services.close_calls()
    body = world["chair"].get(f"{world['base']}/{world['first'].pk}").json()
    assert body["status"] == "screening" and body["can_extend"] is False
    until_local = (timezone.now() + dt.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
    response = world["chair"].post(
        f"{world['base']}/{world['first'].pk}/extensions",
        {"until_local": until_local, "reason": "Trop tard"},
        format="json",
    )
    assert response.status_code == 409 and response.json()["code"] == "submission_locked"


def test_revoke_refused_on_archived_edition(world):
    extension = SubmissionExtension.objects.create(
        submission=world["first"],
        until=timezone.now() + dt.timedelta(days=1),
        reason="Accordée",
        granted_at=timezone.now(),
    )
    world["edition"].status = EditionStatus.ARCHIVED
    world["edition"].save()
    path = f"{world['base']}/{world['first'].pk}/extensions/{extension.pk}/revoke"
    response = world["chair"].post(path)
    assert response.status_code == 409 and response.json()["code"] == "edition_archived"


# --- Clôture (plan L3 §2.2) ----------------------------------------------------------------


def close_now(edition):
    edition.key_dates.filter(code="call_close").update(at=timezone.now() - dt.timedelta(minutes=1))


def test_close_call_moves_submitted_to_screening_idempotently(world):
    """RG-02 et §2.2 : à la clôture, les soumissions passent en recevabilité ; les brouillons
    restent des brouillons ; un second passage ne fait rien."""
    other = complete_submission()
    submit(other)  # autre édition, appel encore ouvert
    close_now(world["edition"])
    call_command("close_call", verbosity=0)
    statuses = dict(Submission.objects.values_list("pk", "status"))
    assert statuses[world["first"].pk] == S.SCREENING
    assert statuses[world["second"].pk] == S.SCREENING
    assert statuses[world["draft"].pk] == S.DRAFT
    assert statuses[other.pk] == S.SUBMITTED
    entry = StatusHistory.objects.filter(to_status=S.SCREENING).first()
    assert entry.actor_id is None and entry.actor_label == "cron:close_call"
    assert CronHeartbeat.objects.get(name="close_call").processed_count == 2
    call_command("close_call", verbosity=0)
    assert CronHeartbeat.objects.get(name="close_call").processed_count == 0
    assert StatusHistory.objects.filter(to_status=S.SCREENING).count() == 2


def test_rg02_close_call_waits_for_extension_deadline(world):
    """RG-02 : une soumission en dérogation reste modifiable jusqu'à son échéance ; elle passe
    en recevabilité au premier passage qui suit."""
    close_now(world["edition"])
    until = timezone.now() + dt.timedelta(hours=2)
    SubmissionExtension.objects.create(
        submission=world["first"], until=until, reason="Accordée", granted_at=timezone.now()
    )
    assert services.close_calls() == 1
    world["first"].refresh_from_db()
    assert world["first"].status == S.SUBMITTED
    assert services.close_calls(now=until + dt.timedelta(minutes=1)) == 1
    world["first"].refresh_from_db()
    assert world["first"].status == S.SCREENING


def test_close_call_ignores_archived_editions(world):
    close_now(world["edition"])
    world["edition"].status = EditionStatus.ARCHIVED
    world["edition"].save()
    assert services.close_calls(actor=Actor.command("cli:test")) == 0
