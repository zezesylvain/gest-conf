"""Endpoint de diagnostic de l'étape L1.0, désactivé par défaut."""

import pytest
from django.test import override_settings
from django.urls import reverse

pytestmark = pytest.mark.django_db

URL = "/v1/diagnostics/request"

EXPECTED_KEYS = {
    "remote_addr",
    "x_forwarded_for",
    "x_real_ip",
    "is_secure",
    "script_name",
    "path_info",
    "client_ip",
}


def test_route():
    assert reverse("core:diagnostics-request") == URL


def test_disabled_by_default(settings):
    assert settings.GESTCONF_DIAGNOSTICS is False


@pytest.mark.parametrize("method", ["get", "post", "options"])
def test_disabled_answers_like_an_unknown_url(client, method):
    response = getattr(client, method)(URL)
    unknown = client.get("/v1/route-inexistante")
    assert response.status_code == 404
    assert response.json() == unknown.json()


@override_settings(GESTCONF_DIAGNOSTICS=True)
def test_enabled_reports_what_django_sees(client):
    response = client.get(
        URL,
        REMOTE_ADDR="10.0.0.1",
        HTTP_X_FORWARDED_FOR="198.51.100.7",
        HTTP_X_REAL_IP="198.51.100.7",
        HTTP_COOKIE="sessionid=secret",
        HTTP_AUTHORIZATION="Bearer secret",
    )
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    payload = response.json()
    assert set(payload) == EXPECTED_KEYS
    assert payload == {
        "remote_addr": "10.0.0.1",
        "x_forwarded_for": "198.51.100.7",
        "x_real_ip": "198.51.100.7",
        "is_secure": False,
        "script_name": "",
        "path_info": URL,
        # Aucun mandataire de confiance par défaut : X-Forwarded-For ignoré.
        "client_ip": "10.0.0.1",
    }
    assert "secret" not in response.content.decode()


@override_settings(GESTCONF_DIAGNOSTICS=True, GESTCONF_TRUSTED_PROXY_COUNT=1)
def test_enabled_reports_computed_client_ip(client):
    response = client.get(URL, REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7")
    assert response.json()["client_ip"] == "198.51.100.7"


@override_settings(GESTCONF_DIAGNOSTICS=True)
def test_enabled_accepts_get_only(client):
    response = client.post(URL)
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"
