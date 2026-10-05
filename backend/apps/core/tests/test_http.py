"""Adresse IP du client et nombre de mandataires de confiance (plan L1 §4.2)."""

import pytest
from django.conf import settings
from django.test import RequestFactory, override_settings
from rest_framework.request import Request
from rest_framework.throttling import ScopedRateThrottle

from apps.core.http import client_ip

CASES = [
    # (REMOTE_ADDR, X-Forwarded-For)
    ("203.0.113.9", None),
    ("10.0.0.1", "198.51.100.7"),
    ("10.0.0.1", "192.0.2.66, 198.51.100.7"),
    ("10.0.0.1", "192.0.2.66,198.51.100.7, 203.0.113.50"),
    ("::1", "2001:db8::1"),
]


def make_request(remote_addr: str, forwarded_for: str | None):
    meta = {"REMOTE_ADDR": remote_addr}
    if forwarded_for is not None:
        meta["HTTP_X_FORWARDED_FOR"] = forwarded_for
    return RequestFactory().get("/", **meta)


def drf_ident(request) -> str:
    return ScopedRateThrottle().get_ident(Request(request))


def test_trusted_proxy_count_feeds_drf_num_proxies():
    """Une seule source : GESTCONF_TRUSTED_PROXY_COUNT alimente NUM_PROXIES de DRF."""
    assert settings.REST_FRAMEWORK["NUM_PROXIES"] == settings.GESTCONF_TRUSTED_PROXY_COUNT


def test_default_trusts_no_proxy():
    """Valeur par défaut sûre : X-Forwarded-For, forgeable, est ignoré."""
    assert settings.GESTCONF_TRUSTED_PROXY_COUNT == 0
    request = make_request("203.0.113.9", "198.51.100.7")
    assert client_ip(request) == "203.0.113.9"


@override_settings(GESTCONF_TRUSTED_PROXY_COUNT=1)
def test_one_trusted_proxy_uses_last_forwarded_address():
    request = make_request("10.0.0.1", "6.6.6.6, 198.51.100.7")
    assert client_ip(request) == "198.51.100.7"


@override_settings(GESTCONF_TRUSTED_PROXY_COUNT=1)
def test_one_trusted_proxy_without_header_uses_remote_addr():
    assert client_ip(make_request("203.0.113.9", None)) == "203.0.113.9"
    assert client_ip(make_request("203.0.113.9", "  ")) == "203.0.113.9"


@override_settings(GESTCONF_TRUSTED_PROXY_COUNT=1)
def test_invalid_forwarded_address_gives_none():
    assert client_ip(make_request("10.0.0.1", "pas-une-ip")) is None


@pytest.mark.parametrize("proxy_count", [0, 1, 2])
@pytest.mark.parametrize(("remote_addr", "forwarded_for"), CASES)
def test_client_ip_matches_drf_throttle_ident(proxy_count, remote_addr, forwarded_for):
    """Même adresse que celle qui sert de clé à la limitation de débit de DRF."""
    rest_framework = {**settings.REST_FRAMEWORK, "NUM_PROXIES": proxy_count}
    with override_settings(GESTCONF_TRUSTED_PROXY_COUNT=proxy_count, REST_FRAMEWORK=rest_framework):
        request = make_request(remote_addr, forwarded_for)
        assert client_ip(request) == drf_ident(request)


def test_missing_remote_addr_gives_none():
    request = RequestFactory().get("/")
    del request.META["REMOTE_ADDR"]
    assert client_ip(request) is None
