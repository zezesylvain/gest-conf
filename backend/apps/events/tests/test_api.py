"""API du pointage et des badges (plan L7, K2 à K5)."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog
from apps.events.models import Checkin
from apps.events.tests.helpers import confirmed, participant
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_category, make_registration

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    return EditionFactory(code="GC27", title_fr="Colloque GEST-CONF 2027")


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}"


def text_of(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def test_k4_scan_api_and_refusals(edition):
    registration = confirmed(edition)
    client = client_for(make_member(edition, Role.VOLUNTEER))
    response = client.post(
        f"{base(edition)}/checkin/scan",
        {"token": registration.qr_token, "device": "Accueil", "idempotency_key": "a1b2c3d4e5"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response["Cache-Control"] == "private, no-store"
    body = response.json()
    assert body["outcome"] == "checked_in"
    assert body["idempotency_key"] == "a1b2c3d4e5"
    assert body["registration"] == {
        "id": registration.pk,
        "reference": registration.reference,
        "name": "Awa Diallo",
        "category": registration.category.code,
        "category_label_fr": registration.category.label_fr,
        "category_label_en": registration.category.label_fr,
        "status": "confirmed",
    }
    assert body["checkin"]["method"] == "scan"
    again = client.post(
        f"{base(edition)}/checkin/scan", {"token": registration.qr_token}, format="json"
    ).json()
    assert again["outcome"] == "already_checked_in"
    unknown = client.post(
        f"{base(edition)}/checkin/scan", {"token": "inconnu-1234567890"}, format="json"
    ).json()
    assert (unknown["outcome"], unknown["registration"], unknown["checkin"]) == (
        "unknown",
        None,
        None,
    )


def test_k4_manual_entry_requires_checkin_manage(edition):
    registration = confirmed(edition)
    path = f"{base(edition)}/checkin/manual"
    volunteer = client_for(make_member(edition, Role.VOLUNTEER))
    assert (
        volunteer.post(path, {"reference": registration.reference}, format="json").status_code
        == 403
    )
    manager = client_for(make_member(edition, Role.OC_MEMBER, oc_function="volunteers"))
    body = manager.post(path, {"reference": registration.reference}, format="json").json()
    assert body["outcome"] == "checked_in"


def test_k5_bundle_and_sync_api(edition):
    registration = confirmed(edition)
    volunteer = client_for(make_member(edition, Role.VOLUNTEER))
    response = volunteer.get(f"{base(edition)}/checkin/bundle")
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    bundle = response.json()
    assert [entry["reference"] for entry in bundle["entries"]] == [registration.reference]
    assert registration.qr_token not in response.content.decode()
    response = volunteer.post(
        f"{base(edition)}/checkin/sync",
        {
            "device": "Téléphone 3",
            "items": [
                {
                    "idempotency_key": "tel3-000001",
                    "token": registration.qr_token,
                    "scanned_at": "2027-06-01T08:12:00Z",
                },
                {
                    "idempotency_key": "tel3-000002",
                    "method": "manual",
                    "reference": registration.reference,
                    "scanned_at": "2027-06-01T08:13:00Z",
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    outcomes = [item["outcome"] for item in response.json()["results"]]
    assert outcomes == ["checked_in", "not_allowed"]
    # Élément mal formé : tout le lot est refusé (400), rien n'est écrit.
    response = volunteer.post(
        f"{base(edition)}/checkin/sync",
        {"items": [{"idempotency_key": "tel3-000003", "scanned_at": "2027-06-01T08:12:00Z"}]},
        format="json",
    )
    assert response.status_code == 400
    assert Checkin.objects.count() == 1


def test_k4_list_cancel_export_and_summary(edition):
    registration = confirmed(edition)
    volunteer = client_for(make_member(edition, Role.VOLUNTEER))
    volunteer.post(f"{base(edition)}/checkin/scan", {"token": registration.qr_token}, format="json")
    assert volunteer.get(f"{base(edition)}/checkin/summary").json() == {
        "confirmed": 1,
        "checked_in": 1,
        "pending": 0,
    }
    assert volunteer.get(f"{base(edition)}/checkin").status_code == 403
    manager = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    rows = manager.get(f"{base(edition)}/checkin?q=diallo").json()["results"]
    assert [row["registration"]["reference"] for row in rows] == [registration.reference]
    checkin_id = rows[0]["id"]
    response = manager.post(
        f"{base(edition)}/checkin/{checkin_id}/cancel", {"reason": "Erreur"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["cancel_reason"] == "Erreur"
    assert manager.get(f"{base(edition)}/checkin").json()["count"] == 0
    assert manager.get(f"{base(edition)}/checkin?cancelled=1").json()["count"] == 1
    volunteer.post(f"{base(edition)}/checkin/scan", {"token": registration.qr_token}, format="json")
    response = manager.get(f"{base(edition)}/checkin/export")
    assert response.status_code == 200
    content = response.content.decode("utf-8-sig")
    assert registration.reference in content and "Awa Diallo" in content
    assert registration.qr_token not in content
    assert AuditLog.objects.filter(action="checkin.exported").count() == 1
    stale = client_for(make_member(edition, Role.ADMIN), recent_auth=False)
    assert stale.get(f"{base(edition)}/checkin/export").status_code == 403


def test_cancel_checkin_of_another_edition_is_404(edition):
    other = EditionFactory()
    registration = confirmed(other)
    volunteer = client_for(make_member(other, Role.VOLUNTEER))
    volunteer.post(
        f"/v1/manage/editions/{other.pk}/checkin/scan",
        {"token": registration.qr_token},
        format="json",
    )
    manager = client_for(make_member(edition, Role.ADMIN))
    response = manager.post(
        f"{base(edition)}/checkin/{Checkin.objects.get().pk}/cancel", {"reason": "x"}, format="json"
    )
    assert response.status_code == 404


# --- Badges (K3) ---------------------------------------------------------------------------------


def test_k3_participant_downloads_own_badge_once_confirmed(edition):
    user = participant("Ŋgóŋ", "Łukasz-Œdipe")
    registration = confirmed(
        edition, user, category=make_category(edition, "etudiant", label_fr="Étudiant")
    )
    client = client_for(user, mfa=False)
    response = client.get(f"/v1/registrations/{registration.pk}/badge")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Cache-Control"] == "private, no-store"
    text = text_of(response.content)
    for expected in (
        "Ŋgóŋ",  # nom en grand, sur deux lignes au besoin
        "Łukasz-Œdipe",
        "ÉTUDIANT",
        registration.reference,
        "Colloque GEST-CONF 2027",
    ):
        assert expected in text
    reader = PdfReader(io.BytesIO(response.content))
    width, height = (float(value) * 25.4 / 72 for value in reader.pages[0].mediabox[2:])
    assert (round(width), round(height)) == (105, 148)
    # Inscription en attente : pas de badge ; celle d'un autre : introuvable.
    pending = make_registration(EditionFactory(), user, status=RegistrationStatus.PENDING)
    assert client.get(f"/v1/registrations/{pending.pk}/badge").status_code == 404
    stranger = client_for(participant(), mfa=False)
    assert stranger.get(f"/v1/registrations/{registration.pk}/badge").status_code == 404
    assert APIClient().get(f"/v1/registrations/{registration.pk}/badge").status_code == 401


def test_k3_committee_sheets_by_batch_and_category(edition, monkeypatch):
    monkeypatch.setattr("apps.events.badges.BATCH_SIZE", 3)
    students = make_category(edition, "etudiant", label_fr="Étudiant", badge_color="#FFD600")
    others = make_category(edition, "chercheur", label_fr="Chercheur")
    for index in range(4):
        confirmed(edition, participant("P", f"Etudiant{index}"), category=students)
    confirmed(edition, participant("P", "Chercheur"), category=others)
    make_registration(edition, participant(), status=RegistrationStatus.PENDING, category=students)
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="logistics"))
    assert client.get(f"{base(edition)}/registrations/badges/batches?category=etudiant").json() == {
        "count": 4,
        "batch_size": 3,
        "batches": 2,
    }
    response = client.get(f"{base(edition)}/registrations/badges?category=etudiant&batch=2")
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    reader = PdfReader(io.BytesIO(response.content))
    assert len(reader.pages) == 1
    assert "Etudiant3" in text_of(response.content)
    assert "Chercheur" not in text_of(response.content)
    assert client.get(f"{base(edition)}/registrations/badges?batch=3").status_code == 404
    assert client.get(f"{base(edition)}/registrations/badges?batch=0").status_code == 400
    entry = AuditLog.objects.get(action="registrations.badges_downloaded")
    assert entry.after == {"count": 1, "category": "etudiant", "batch": 2}


def test_k2_regenerate_token_api(edition):
    registration = confirmed(edition)
    old = registration.qr_token
    manager = client_for(make_member(edition, Role.OC_MEMBER, oc_function="logistics"))
    path = f"{base(edition)}/registrations/{registration.pk}/regenerate-token"
    assert manager.post(path, {"reason": ""}, format="json").status_code == 400
    assert manager.post(path, {"reason": "Badge perdu"}, format="json").status_code == 204
    registration.refresh_from_db()
    assert registration.qr_token != old
    volunteer = client_for(make_member(edition, Role.VOLUNTEER))
    body = volunteer.post(f"{base(edition)}/checkin/scan", {"token": old}, format="json").json()
    assert body["outcome"] == "replaced"
    assert volunteer.post(path, {"reason": "x"}, format="json").status_code == 403


def test_k3_category_badge_color_is_validated(edition):
    category = make_category(edition, "etudiant")
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))
    path = f"{base(edition)}/registrations/categories/{category.pk}"
    response = client.patch(path, {"badge_color": "#12"}, format="json")
    assert response.status_code == 400
    assert "badge_color" in response.json()["fields"]
    response = client.patch(path, {"badge_color": "#1565C0"}, format="json")
    assert response.status_code == 200
    assert response.json()["badge_color"] == "#1565C0"
