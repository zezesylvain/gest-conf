"""API des tâches du CO (plan L8, N3) et registre des données personnelles (N15)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.personal_data import export_sections
from apps.logistics.models import Task

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n%%EOF\n"


@pytest.fixture
def edition():
    return EditionFactory(timezone="Africa/Abidjan")


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/tasks"


def test_n3_task_api_round_trip_with_revision(edition, settings, tmp_path):
    settings.GESTCONF_PRIVATE_FILES_DIR = str(tmp_path)
    chair = make_member(edition, Role.CHAIR)
    program = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.PROGRAM)
    client = client_for(chair)
    members = client.get(f"{base(edition)}/members").json()
    assert {person["id"] for person in members} == {chair.pk, program.pk}
    response = client.post(
        base(edition),
        {"title": "Badges", "assignee": program.pk, "due_date": "2000-01-01"},
        format="json",
    )
    assert response.status_code == 201
    created = response.json()
    assert created["overdue"] is True and created["assignee"]["id"] == program.pk
    assert created["comments"] == [] and created["revision"] == 1
    task_url = f"{base(edition)}/{created['id']}"
    # If-Match périmé : 412.
    response = client.patch(task_url, {"status": "done"}, format="json", HTTP_IF_MATCH="7")
    assert (response.status_code, response.json()["code"]) == (412, "stale_revision")
    response = client.patch(task_url, {"status": "done"}, format="json", HTTP_IF_MATCH="1")
    assert response.status_code == 200
    assert (response.json()["revision"], response.json()["overdue"]) == (2, False)
    # Commentaire et pièce jointe ; le détail les porte, la liste les compte.
    client.post(f"{task_url}/comments", {"body": "Imprimés."}, format="json")
    response = client.post(
        f"{task_url}/attachments",
        {"file": SimpleUploadedFile("bon.pdf", PDF, "application/pdf")},
        format="multipart",
    )
    assert response.status_code == 201
    attachment = response.json()["attachments"][0]
    download = client.get(f"{task_url}/attachments/{attachment['id']}")
    assert download.status_code == 200 and download.content == PDF
    assert download["Cache-Control"] == "private, no-store"
    listed = client.get(base(edition)).json()
    assert (listed[0]["comment_count"], listed[0]["attachment_count"]) == (1, 1)
    # Le CO « programme » voit ses tâches ; une tâche d'une autre édition est introuvable.
    mine = client_for(program).get(f"{base(edition)}?mine=true").json()
    assert [row["title"] for row in mine] == ["Badges"]
    other = Task.objects.create(edition=EditionFactory(), title="Ailleurs")
    assert client.get(f"{base(edition)}/{other.pk}").status_code == 404
    # Archivée : hors de la liste active, visible dans la liste des archives.
    client.post(f"{task_url}/archive")
    assert client.get(base(edition)).json() == []
    assert len(client.get(f"{base(edition)}?archived=true").json()) == 1


def test_n15_tasks_in_the_personal_data_export(edition):
    chair = make_member(edition, Role.CHAIR)
    task = Task.objects.create(
        edition=edition, title="Salle", assignee=chair, due_date=dt.date(2027, 5, 1)
    )
    task.comments.create(author=chair, body="Réservée.")
    section = export_sections(chair)
    assert section["tasks"][0]["title"] == "Salle"
    assert section["tasks"][0]["assigned_to_me"] is True
    assert section["task_comments"] == [
        {"edition": edition.code, "task": "Salle", "body": "Réservée."}
    ]
