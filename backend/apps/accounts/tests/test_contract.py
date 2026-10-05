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
