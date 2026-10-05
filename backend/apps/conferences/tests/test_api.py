"""API de l'édition : édition publique (§9.3), saisie à l'heure locale, journal (§7.4)."""

import datetime as dt

import pytest
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences import services
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import (
    EditionFactory,
    KeyDateFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from apps.core.actor import Actor
from apps.core.audit import record

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")
CURRENT = "/v1/public/editions/current"


def published_current_edition(**fields):
    edition = EditionFactory(status=EditionStatus.PUBLISHED, **fields)
    services.set_current_edition(edition.conference, edition, actor=COMMAND)
    return edition


# --- Édition publique courante -------------------------------------------------------------


def test_public_current_edition_404_when_none():
    response = APIClient().get(CURRENT)
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_public_current_edition_hides_draft():
    edition = EditionFactory()
    services.set_current_edition(edition.conference, edition, actor=COMMAND)
    assert APIClient().get(CURRENT).status_code == 404


def test_public_current_edition_hides_internal_items():
    edition = published_current_edition()
    TrackFactory(edition=edition, code="actif")
    TrackFactory(edition=edition, code="inactif", is_active=False)
    SubmissionTypeFactory(edition=edition, code="oral")
    KeyDateFactory(edition=edition, code="call_open")
    KeyDateFactory(
        edition=edition,
        code="comite",
        label_fr="Réunion du comité",
        is_public=False,
        at=dt.datetime(2027, 2, 1, tzinfo=dt.UTC),
    )
    response = APIClient().get(CURRENT)
    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=300"
    body = response.json()
    assert body["code"] == edition.code
    assert [track["code"] for track in body["tracks"]] == ["actif"]
    assert [key_date["code"] for key_date in body["key_dates"]] == ["call_open"]
    # Aucun champ interne (statut, confidentialité, identifiants).
    assert not {"id", "status", "double_blind", "reviewers_per_submission"} & set(body)


# --- Dates clés à l'heure de l'édition (D13) ------------------------------------------------


def test_key_date_api_uses_local_time():
    edition = EditionFactory(timezone="Europe/Paris")
    client = client_for(make_member(edition, Role.CHAIR))
    url = f"/v1/manage/editions/{edition.pk}/key-dates"
    response = client.post(url, {"code": "call_close", "at_local": "2027-07-01T23:59"})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["at"].startswith("2027-07-01T21:59")
    assert body["at_local"].startswith("2027-07-01T23:59")
    response = client.post(url, {"code": "call_open", "at_local": "2027-03-28T02:30"})
    assert response.status_code == 400
    assert "at_local" in response.json()["fields"]


# --- Journal de l'édition (§7.4) ------------------------------------------------------------


def test_audit_lists_only_entries_of_the_edition():
    edition, other = EditionFactory(), EditionFactory()
    client = client_for(make_member(edition, Role.ADMIN))
    services.update_edition(edition, {"venue": "Palais"}, actor=COMMAND)
    services.update_edition(other, {"venue": "Stade"}, actor=COMMAND)
    record("account.login", actor=COMMAND)  # entrée sans édition : jamais visible ici
    response = client.get(f"/v1/manage/editions/{edition.pk}/audit")
    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()["results"]]
    assert actions == ["edition.updated"]
    entry = response.json()["results"][0]
    assert not {"ip", "user_agent"} & set(entry)


def test_audit_filters():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.ADMIN))
    services.update_edition(edition, {"venue": "Palais"}, actor=COMMAND)
    services.create_track(edition, {"code": "t1", "name_fr": "T", "name_en": "T"}, actor=COMMAND)
    url = f"/v1/manage/editions/{edition.pk}/audit"
    by_prefix = client.get(url, {"action": "track."}).json()["results"]
    assert [entry["action"] for entry in by_prefix] == ["track.created"]
    exact = client.get(url, {"action": "edition.updated"}).json()["results"]
    assert len(exact) == 1
    future = client.get(url, {"since": "2100-01-01T00:00:00Z"}).json()["results"]
    assert future == []
