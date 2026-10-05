"""Tests de contrat d'allauth headless (décision D4, plan L1 §9.2, §4.5).

La façade Angular ``AuthApi`` est écrite à la main : ces tests figent les champs
qu'elle consomme (``status``, ``data.user``, ``data.flows[].id``,
``meta.is_authenticated``, ``errors[].code`` et ``param``), ainsi que la structure
interne des enregistrements d'authentification lue par ``RecentAuthRequired`` (L1.5).
Ils doivent échouer à une montée de version d'allauth qui les changerait.
"""

import time

import allauth
import pytest

from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.helpers import (
    AUTH,
    AUTH_RECORDS_SESSION_KEY,
    flow_ids,
    login,
    post,
    signup,
)

pytestmark = pytest.mark.django_db


def test_allauth_version_is_pinned():
    """Toute montée de version repasse par ces tests et la liste de contrôle du plan."""
    assert allauth.__version__ == "65.19.7"


def test_anonymous_session_contract(client):
    body = client.get(f"{AUTH}/auth/session").json()
    assert body["status"] == 401
    assert body["meta"] == {"is_authenticated": False}
    assert {"login", "signup"} <= set(flow_ids(client.get(f"{AUTH}/auth/session")))


def test_authenticated_session_contract(client):
    user = VerifiedUserFactory()
    body = login(client, user.email).json()
    assert body["status"] == 200
    assert body["meta"]["is_authenticated"] is True
    assert body["data"]["user"]["id"] == user.pk
    assert body["data"]["user"]["email"] == user.email
    assert client.get(f"{AUTH}/auth/session").json()["data"]["user"]["id"] == user.pk


def test_pending_verification_flow_contract(client):
    body = signup(client, "contrat@example.org").json()
    assert body["status"] == 401
    pending = [flow for flow in body["data"]["flows"] if flow.get("is_pending")]
    assert [flow["id"] for flow in pending] == ["verify_email"]


def test_error_contract(client):
    user = VerifiedUserFactory()
    body = login(client, user.email, "mauvais-mot-de-passe").json()
    assert body["status"] == 400
    error = body["errors"][0]
    assert set(error) >= {"message", "code", "param"}
    assert (error["code"], error["param"]) == ("email_password_mismatch", "password")


def test_reauthentication_flow_contract(client):
    user = VerifiedUserFactory()
    login(client, user.email)
    session = client.session
    records = session[AUTH_RECORDS_SESSION_KEY]
    records[-1]["at"] -= 600
    session[AUTH_RECORDS_SESSION_KEY] = records
    session.save()
    response = post(client, "account/email", {"email": "autre@example.org"})
    assert response.status_code == 401
    assert response.json()["meta"]["is_authenticated"] is True
    assert flow_ids(response) == ["reauthenticate"]


def test_authentication_records_structure(client):
    """§4.5 : ``RecentAuthRequired`` lira ``records[-1]["at"]`` (horodatage ``time.time()``)."""
    user = VerifiedUserFactory()
    before = time.time()
    login(client, user.email)
    records = client.session[AUTH_RECORDS_SESSION_KEY]
    assert records[-1]["method"] == "password"
    assert before <= records[-1]["at"] <= time.time()


# --- 2FA (L1.6) : champs consommés par AuthApi (web/projects/shared/src/lib/auth) -----------


def test_mfa_endpoints_contract(django_capture_on_commit_callbacks):
    from apps.accounts.tests.roles_helpers import client_for
    from apps.accounts.tests.test_mfa import totp_code

    user = VerifiedUserFactory()
    client = client_for(user, mfa=False)
    assert client.get(f"{AUTH}/account/authenticators").json() == {"status": 200, "data": []}
    pending = client.get(f"{AUTH}/account/authenticators/totp")
    assert pending.status_code == 404
    meta = pending.json()["meta"]
    assert set(meta) == {"secret", "totp_url"}
    wrong = post(client, "account/authenticators/totp", {"code": "000000"}).json()
    assert (wrong["status"], wrong["errors"][0]["code"], wrong["errors"][0]["param"]) == (
        400,
        "incorrect_code",
        "code",
    )
    with django_capture_on_commit_callbacks(execute=True):
        active = post(client, "account/authenticators/totp", {"code": totp_code(meta["secret"])})
    assert active.json()["data"]["type"] == "totp"
    listed = client.get(f"{AUTH}/account/authenticators").json()["data"]
    assert [item["type"] for item in listed] == ["totp", "recovery_codes"]
    assert {"total_code_count", "unused_code_count"} <= set(listed[1])
    codes = client.get(f"{AUTH}/account/authenticators/recovery-codes").json()["data"]
    assert len(codes["unused_codes"]) == 10
    regenerated = post(client, "account/authenticators/recovery-codes").json()["data"]
    assert regenerated["unused_codes"] != codes["unused_codes"]
    # Compte 2FA : ajout d'adresse bloqué en mode « lien » (D6, option (a) et RG-20).
    blocked = post(client, "account/email", {"email": "autre@example.org"}).json()
    assert blocked["errors"][0]["code"] == "add_email_blocked"
    assert client.delete(f"{AUTH}/account/authenticators/totp").json() == {"status": 200}


def test_stale_mfa_action_asks_for_reauthentication():
    """Action 2FA sans authentification récente : 401, flux ``reauthenticate`` et
    ``mfa_reauthenticate`` (sans ``is_pending``), session toujours authentifiée."""
    from apps.accounts.tests.roles_helpers import client_for, enable_totp

    user = VerifiedUserFactory()
    enable_totp(user)
    client = client_for(user, mfa=False, recent_auth=False)
    body = client.delete(f"{AUTH}/account/authenticators/totp").json()
    assert body["status"] == 401
    assert body["meta"]["is_authenticated"] is True
    assert flow_ids_of(body) == ["reauthenticate", "mfa_reauthenticate"]


def flow_ids_of(body: dict) -> list[str]:
    return [flow["id"] for flow in body["data"]["flows"]]
