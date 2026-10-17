"""Sessions pré-établies du test de charge (plan L9, S5)."""

from __future__ import annotations

import io
import json
import stat

import pytest
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.core.management.base import CommandError
from rest_framework.test import APIClient

from apps.qa.volume import seed_volume

pytestmark = pytest.mark.django_db

SIZES = {"submissions": 4, "reviewers": 3, "participants": 6, "drafts": 4}
COUNTS = ["--committees", "2", "--reviewers", "2", "--authors", "2", "--participants", "2"]


def open_file(tmp_path, *extra):
    path = tmp_path / "sessions.json"
    output = io.StringIO()
    call_command(
        "loadtest_sessions",
        "--confirm-fictitious",
        "--output",
        str(path),
        *COUNTS,
        "--newcomers",
        "2",
        *extra,
        stdout=output,
    )
    return path, json.loads(path.read_text("utf-8"))


def client_from(data, item):
    client = APIClient(enforce_csrf_checks=True)
    client.cookies[data["cookies"]["session"]] = item["session"]
    client.cookies[data["cookies"]["csrf"]] = item["csrf_cookie"]
    client.defaults["HTTP_X_CSRFTOKEN"] = item["csrf_token"]
    return client


def test_s5_sessions_are_usable_with_mfa_and_csrf(tmp_path):
    seed_volume(**SIZES)
    path, data = open_file(tmp_path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert {name: len(items) for name, items in data["personas"].items()} == {
        "committee": 2,
        "reviewer": 2,
        "author": 2,
        "participant": 2,
        "newcomer": 2,
    }
    evaluation, call = data["editions"]["evaluation"], data["editions"]["call"]
    scopes = sorted(item["scope"] for item in data["personas"]["committee"])
    assert scopes == ["call", "evaluation"]
    # Relecteur : route soumise à la 2FA (MfaVerified).
    reviewer = client_from(data, data["personas"]["reviewer"][0])
    assert reviewer.get(f"/v1/manage/editions/{evaluation}/reviews/assignments").status_code == 200
    # Comité : liste paginée.
    (chair_item,) = [i for i in data["personas"]["committee"] if i["scope"] == "evaluation"]
    chair = client_from(data, chair_item)
    assert chair.get(f"/v1/manage/editions/{evaluation}/submissions").status_code == 200
    # Écriture protégée par le CSRF : devis puis inscription d'un nouveau participant.
    newcomer = client_from(data, data["personas"]["newcomer"][0])
    assert newcomer.post("/v1/registrations/quote", {"category": "chercheur"}).status_code == 200
    order = {"category": "chercheur", "method": "transfer"}
    assert newcomer.post("/v1/registrations", order).status_code == 201
    # Auteur : son brouillon de l'édition en appel.
    author = client_from(data, data["personas"]["author"][0])
    (draft,) = author.get("/v1/submissions").json()
    assert draft["status"] == "draft"
    participant = client_from(data, data["personas"]["participant"][0])
    assert participant.get("/v1/registrations").json()[0]["edition"]["id"] == call


def test_s5_sessions_refused_without_confirmation_or_volume(tmp_path):
    with pytest.raises(CommandError, match="confirm-fictitious"):
        call_command("loadtest_sessions", "--output", str(tmp_path / "x.json"))
    with pytest.raises(CommandError, match="seed_volume"):
        call_command("loadtest_sessions", "--confirm-fictitious", "--output", str(tmp_path / "x"))


def test_s5_sessions_file_is_never_overwritten_and_revoke_deletes(tmp_path):
    seed_volume(**SIZES)
    path, data = open_file(tmp_path)
    with pytest.raises(CommandError, match="existe déjà"):
        open_file(tmp_path)
    keys = [item["session"] for items in data["personas"].values() for item in items]
    assert Session.objects.filter(session_key__in=keys).count() == len(keys)
    call_command("loadtest_sessions", "--revoke", str(path), stdout=io.StringIO())
    assert not Session.objects.filter(session_key__in=keys).exists()
