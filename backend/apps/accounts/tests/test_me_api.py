"""Espace compte de l'API : /v1/me, préférences, profil, consentements (plan L1 §9.3)."""

import pytest

from apps.accounts.consents import CURRENT_TEXT_VERSIONS
from apps.accounts.models import Consent, Profile
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.helpers import JSON, login
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return VerifiedUserFactory(email="awa@univ.ci")


@pytest.fixture
def me_client(client, user):
    assert login(client, user.email).status_code == 200
    return client


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/v1/me"),
        ("patch", "/v1/me/preferences"),
        ("get", "/v1/me/profile"),
        ("patch", "/v1/me/profile"),
        ("get", "/v1/me/consents"),
        ("post", "/v1/me/consents"),
    ],
)
def test_me_endpoints_require_authentication(client, method, path):
    response = getattr(client, method)(path, {}, content_type=JSON)
    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"


def test_me_returns_own_identity(me_client, user):
    assert me_client.get("/v1/me").json() == {
        "id": user.pk,
        "email": "awa@univ.ci",
        "locale": "fr",
        "profile_complete": False,
        "privacy_notice_pending": True,
        "editions": [],
        "pending_invitations": [],
    }


def test_preferences_update_locale_and_is_audited(me_client, user):
    response = me_client.patch("/v1/me/preferences", {"locale": "en"}, content_type=JSON)
    assert response.status_code == 200
    assert response.json()["locale"] == "en"
    user.refresh_from_db()
    assert user.locale == "en"
    entry = AuditLog.objects.get(action="account.preferences_updated")
    assert (entry.before, entry.after) == ({"locale": "fr"}, {"locale": "en"})


def test_preferences_reject_unknown_locale(me_client):
    response = me_client.patch("/v1/me/preferences", {"locale": "de"}, content_type=JSON)
    assert response.status_code == 400
    assert "locale" in response.json()["fields"]


def test_profile_is_created_on_first_write_and_audit_has_no_values(me_client, user):
    assert me_client.get("/v1/me/profile").json()["is_complete"] is False
    assert not Profile.objects.exists()
    response = me_client.patch(
        "/v1/me/profile",
        {"first_name": "Awa", "last_name": "Koné", "orcid": "0000-0002-1694-233x"},
        content_type=JSON,
    )
    assert response.status_code == 200
    assert response.json()["orcid"] == "0000-0002-1694-233X"
    profile = Profile.objects.get(user=user)
    assert profile.last_name == "Koné"
    entry = AuditLog.objects.get(action="profile.updated")
    # Seulement la liste des champs modifiés, jamais leurs valeurs (§7.3).
    assert entry.after == {"fields": ["first_name", "last_name", "orcid"]}
    assert "Koné" not in str(entry.before) + str(entry.after)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("orcid", "0000-0002-1825-0098"),  # mauvaise clé de contrôle
        ("orcid", "0000-0002-1825"),
        ("country", "XX"),
        ("country", "FRA"),
        ("title", "sir"),
        ("bio", "x" * 2001),
    ],
)
def test_profile_validation(me_client, field, value):
    response = me_client.patch("/v1/me/profile", {field: value}, content_type=JSON)
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    assert field in response.json()["fields"]


def test_profile_ignores_mass_assignment(me_client, user):
    """Assignation de masse : seuls les champs déclarés du profil sont pris en compte."""
    response = me_client.patch(
        "/v1/me/profile",
        {"first_name": "Awa", "user": 999, "email": "pirate@example.org", "is_active": False},
        content_type=JSON,
    )
    assert response.status_code == 200
    user.refresh_from_db()
    assert (user.email, user.is_active) == ("awa@univ.ci", True)


def test_profile_patch_requires_csrf_token(user, csrf_api_client):
    """§4.6, cas 2 : DRF avec une session authentifiée → 403 csrf_failed."""
    csrf_api_client.force_login(user)
    response = csrf_api_client.patch("/v1/me/profile", {"first_name": "X"}, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_privacy_notice_acknowledgement_clears_pending_flag(me_client, user):
    response = me_client.post(
        "/v1/me/consents",
        {"kind": "privacy_notice", "granted": True, "source": "first_login"},
        content_type=JSON,
    )
    assert response.status_code == 201
    assert response.json()["text_version"] == CURRENT_TEXT_VERSIONS["privacy_notice"]
    assert me_client.get("/v1/me").json()["privacy_notice_pending"] is False
    consent = Consent.objects.get()
    assert consent.ip == "127.0.0.1"
    assert AuditLog.objects.filter(action="consent.granted").count() == 1


def test_new_notice_version_makes_acknowledgement_pending_again(me_client, monkeypatch):
    me_client.post(
        "/v1/me/consents", {"kind": "privacy_notice", "granted": True}, content_type=JSON
    )
    monkeypatch.setitem(CURRENT_TEXT_VERSIONS, "privacy_notice", "2027-01-v1")
    assert me_client.get("/v1/me").json()["privacy_notice_pending"] is True


def test_privacy_notice_cannot_be_withdrawn(me_client):
    response = me_client.post(
        "/v1/me/consents", {"kind": "privacy_notice", "granted": False}, content_type=JSON
    )
    assert response.status_code == 400
    assert "granted" in response.json()["fields"]


def test_optional_consent_grant_then_withdraw_keeps_history(me_client):
    for granted in (True, False):
        me_client.post(
            "/v1/me/consents", {"kind": "directory_listing", "granted": granted}, content_type=JSON
        )
    body = me_client.get("/v1/me/consents").json()
    states = {state["kind"]: state for state in body["states"]}
    assert states["directory_listing"]["granted"] is False
    assert states["privacy_notice"]["recorded_at"] is None
    assert [row["granted"] for row in body["history"]] == [False, True]
    assert "ip" not in body["history"][0]
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"consent.granted", "consent.withdrawn"} <= actions


def test_consent_source_command_is_not_accepted_from_api(me_client):
    response = me_client.post(
        "/v1/me/consents",
        {"kind": "directory_listing", "granted": True, "source": "command"},
        content_type=JSON,
    )
    assert response.status_code == 400
