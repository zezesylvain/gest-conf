"""API des attestations (plan L7, K9 à K11, K18, K19) et vérification publique (K10)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.core.models import Job
from apps.events.models import Certificate
from apps.events.services import certificates as service
from apps.events.tests.certificate_helpers import (
    TEST_PASSWORD,
    pkcs12_file,
    png,
    present,
    signatory,
)
from apps.events.tests.certificate_helpers import edition as make_edition

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    return make_edition()


@pytest.fixture
def manager(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/certificates"


def test_k11_overview_issue_list_pdf_revoke(edition, manager):
    signatory(edition)
    registration = present(edition)
    overview = {row["nature"]: row for row in manager.get(f"{base(edition)}/overview").json()}
    assert overview["participation"] | {} == {
        "nature": "participation",
        "enabled": True,
        "ready": True,
        "problem": "",
        "eligible": 1,
        "issued": 0,
        "revoked": 0,
        "unreachable": 0,
        "pending": False,
    }
    assert overview["review"]["enabled"] is False
    response = manager.post(f"{base(edition)}/issue", {"nature": "participation"}, format="json")
    assert response.status_code == 202, response.content
    job = Job.objects.get(pk=response.json()["job_id"])
    assert manager.get(f"{base(edition)}/overview").json()[0]["pending"] is True
    service.issue_job(job)
    rows = manager.get(f"{base(edition)}?nature=participation").json()["results"]
    assert [row["user_id"] for row in rows] == [registration.user_id]
    assert "verification_code" not in rows[0] and "sha256" not in rows[0]
    certificate_id = rows[0]["id"]
    response = manager.get(f"{base(edition)}/{certificate_id}/pdf")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    response = manager.post(
        f"{base(edition)}/{certificate_id}/revoke", {"reason": "Erreur"}, format="json"
    )
    assert response.json()["revoked_at"] is not None
    assert manager.get(f"{base(edition)}?revoked=1").json()["count"] == 1


def test_k18_issue_refused_without_signatory(edition, manager):
    present(edition)
    response = manager.post(f"{base(edition)}/issue", {"nature": "participation"}, format="json")
    assert (response.status_code, response.json()["code"]) == (409, "signatory_missing")
    assert manager.get(f"{base(edition)}/overview").json()[0]["problem"] == "signatory_missing"


def test_k19_templates_signatories_and_preview(edition, manager):
    _user, signature = signatory(edition, designate=())
    rows = {row["nature"]: row for row in manager.get(f"{base(edition)}/templates").json()}
    assert set(rows) == {"participation", "presentation", "review", "letter"}
    assert rows["presentation"]["placeholders"] == [
        "dates",
        "edition",
        "name",
        "reference",
        "title",
        "venue",
    ]
    assert rows["participation"]["signatory"] is None
    signatories = manager.get(f"{base(edition)}/signatories").json()
    assert signatories == [
        {
            "id": signature.pk,
            "display_name": "Pr Awa Diallo",
            "title_fr": "Présidente du comité d'organisation",
            "title_en": "Organising committee chair",
        }
    ]
    response = manager.patch(
        f"{base(edition)}/templates/participation",
        {"signatory": signature.pk, "footer_fr": "Université de test"},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["signatory"]["id"] == signature.pk
    response = manager.patch(
        f"{base(edition)}/templates/participation", {"body_fr": "{inconnu}"}, format="json"
    )
    assert response.status_code == 400 and "body_fr" in response.json()["fields"]
    assert manager.patch(f"{base(edition)}/templates/autre", {}, format="json").status_code == 404
    response = manager.get(f"{base(edition)}/templates/participation/preview")
    assert response.status_code == 200 and response.content.startswith(b"%PDF")


def test_k19_settings_header_and_signing_key(edition, manager):
    body = manager.get(f"{base(edition)}/settings").json()
    assert body == {
        "signing_mode": "image",
        "review_enabled": False,
        "layout": "signature_right",
        "has_header": False,
        "header_width": None,
        "header_height": None,
        "signing_key": None,
        "signing_available": True,
    }
    body = manager.patch(
        f"{base(edition)}/settings",
        {"review_enabled": True, "layout": "signature_left"},
        format="json",
    ).json()
    assert (body["review_enabled"], body["layout"]) == (True, "signature_left")
    response = manager.put(
        f"{base(edition)}/settings/header",
        {"file": SimpleUploadedFile("logo.png", png((800, 160)), "image/png")},
        format="multipart",
    )
    assert response.json()["has_header"] is True
    assert manager.get(f"{base(edition)}/settings/header")["Content-Type"] == "image/png"
    data, _certificate = pkcs12_file()
    response = manager.put(
        f"{base(edition)}/settings/signing-key",
        {"file": SimpleUploadedFile("cle.p12", data), "password": TEST_PASSWORD},
        format="multipart",
    )
    assert response.status_code == 200, response.content
    assert response.json()["signing_key"]["subject"] == "CN=Université de test"
    assert TEST_PASSWORD not in response.content.decode()
    body = manager.patch(f"{base(edition)}/settings", {"signing_mode": "pades"}, format="json")
    assert body.json()["signing_mode"] == "pades"
    response = manager.delete(f"{base(edition)}/settings/signing-key")
    assert response.json()["signing_mode"] == "image"
    stale = client_for(make_member(edition, Role.ADMIN), recent_auth=False)
    response = stale.patch(f"{base(edition)}/settings", {"review_enabled": False}, format="json")
    assert response.json()["code"] == "reauthentication_required"


def test_k15_my_certificates_and_download(edition):
    signatory(edition)
    registration = present(edition)
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    client = client_for(registration.user, mfa=False)
    rows = client.get("/v1/me/certificates").json()
    assert [(row["id"], row["nature"], row["revoked"]) for row in rows] == [
        (certificate.pk, "participation", False)
    ]
    assert rows[0]["verification_url"].endswith(f"/verification/{certificate.verification_code}")
    response = client.get(f"/v1/me/certificates/{certificate.pk}/pdf")
    assert response.status_code == 200
    stranger = client_for(make_member(edition, Role.ATTENDEE), mfa=False)
    assert stranger.get(f"/v1/me/certificates/{certificate.pk}/pdf").status_code == 404
    service.revoke(certificate, reason="x", actor=service.SYSTEM)
    assert client.get(f"/v1/me/certificates/{certificate.pk}/pdf").status_code == 404
    assert client.get("/v1/me/certificates").json()[0]["revoked"] is True
    assert APIClient().get("/v1/me/certificates").status_code == 401


def test_k10_public_verification(edition):
    signatory(edition)
    present(edition)
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    client = APIClient()
    response = client.get(f"/v1/public/certificates/{certificate.verification_code}")
    assert response.status_code == 200
    assert "noindex" in response["X-Robots-Tag"]
    body = response.json()
    assert body["status"] == "valid" and body["nature"] == "participation"
    assert set(body) == {
        "kind",
        "nature",
        "name",
        "edition_title_fr",
        "edition_title_en",
        "edition_start",
        "edition_end",
        "issued_at",
        "status",
        "revoked_at",
    }
    unknown = client.get(f"/v1/public/certificates/{'A' * 26}")
    malformed = client.get("/v1/public/certificates/zz")
    assert unknown.status_code == malformed.status_code == 404
    assert unknown.json() == malformed.json()


def test_k10_public_verification_is_throttled(edition, settings):
    from rest_framework.throttling import ScopedRateThrottle

    rates = dict(ScopedRateThrottle.THROTTLE_RATES, certificate_verify="2/min")
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": rates}
    ScopedRateThrottle.THROTTLE_RATES = rates
    try:
        client = APIClient()
        codes = [client.get(f"/v1/public/certificates/{'B' * 26}").status_code for _ in range(3)]
    finally:
        from django.conf import settings as django_settings

        ScopedRateThrottle.THROTTLE_RATES = django_settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert codes == [404, 404, 429]
