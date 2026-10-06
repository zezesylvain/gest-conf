"""Client CinetPay (API v1, bilan de L6.0), HTTP simulé : aucun appel réseau réel. Les
formes d'appel et de réponse suivent le SDK Python officiel (cinetpay-python 0.1.0)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
import requests
from django.core.cache import cache

from apps.payments.providers.base import Customer, InvalidNotification, ProviderError
from apps.payments.providers.cinetpay import TOKEN_CACHE_KEY, CinetPayProvider

# Jeton gardé dans le cache de la base (partagé entre processus).
pytestmark = pytest.mark.django_db


class FakeHttp:
    """Réponses programmées par (méthode, chemin) ; requêtes enregistrées."""

    def __init__(self):
        self.routes: dict[tuple[str, str], list[tuple[int, dict]]] = {}
        self.calls: list[dict] = []

    def add(self, method, path, status, body):
        self.routes.setdefault((method, path), []).append((status, body))

    def __call__(self, method, url, json=None, headers=None, timeout=None):
        path = url.split("cinetpay.net", 1)[1]
        self.calls.append({"method": method, "path": path, "json": json, "headers": headers})
        status, body = self.routes[(method, path)].pop(0)
        return SimpleNamespace(status_code=status, json=lambda: body)


@pytest.fixture
def http(monkeypatch, settings):
    settings.CINETPAY_API_KEY = "sk_test_cle"
    settings.CINETPAY_API_PASSWORD = "mot-de-passe"
    settings.CINETPAY_SANDBOX = True
    cache.delete(TOKEN_CACHE_KEY)
    fake = FakeHttp()
    monkeypatch.setattr(requests, "request", fake)
    return fake


def payment(reference="GC27-12-1", amount="25000", currency="XOF"):
    return SimpleNamespace(reference=reference, amount=Decimal(amount), currency=currency)


def initiate(provider, item=None, **urls):
    return provider.initiate(
        item or payment(),
        customer=Customer(first_name="A", last_name="Zadi", email="awa@example.org"),
        designation="GC27 GC27-I00012",
        language="fr",
        success_url=urls.get("success", "https://c.test/compte/mon-inscription?paiement=GC27-12-1"),
        failed_url="https://c.test/compte/mon-inscription?paiement=GC27-12-1&echec=1",
        notify_url="https://c.test/api/v1/payments/webhook/cinetpay",
    )


def test_initiation_body_token_and_sandbox_host(http):
    http.add("POST", "/v1/oauth/login", 200, {"code": 200, "access_token": "jwt-1"})
    http.add(
        "POST",
        "/v1/payment",
        200,
        {
            "code": 200,
            "status": "OK",
            "payment_url": "https://checkout.cinetpay.net/p/abc",
            "payment_token": "pt",
            "notify_token": "nt-secret",
            "transaction_id": "CP-1",
        },
    )
    result = initiate(CinetPayProvider())
    assert (result.payment_url, result.notify_token, result.provider_reference) == (
        "https://checkout.cinetpay.net/p/abc",
        "nt-secret",
        "CP-1",
    )
    login, pay = http.calls
    assert login["json"] == {"api_key": "sk_test_cle", "api_password": "mot-de-passe"}
    assert pay["headers"]["Authorization"] == "Bearer jwt-1"
    body = pay["json"]
    assert body["amount"] == 25000 and isinstance(body["amount"], int)
    assert body["merchant_transaction_id"] == "GC27-12-1"
    assert (body["channel"], body["currency"], body["lang"]) == ("PUSH", "XOF", "fr")
    # Prénom d'une lettre complété : l'API exige 2 caractères au moins.
    assert len(body["client_first_name"]) >= 2
    # Jeton gardé en cache : pas de nouvelle authentification.
    http.add("GET", "/v1/payment/GC27-12-1", 200, {"status": "PENDING"})
    CinetPayProvider().check(payment())
    assert [call["path"] for call in http.calls].count("/v1/oauth/login") == 1


def test_expired_token_is_renewed_once(http):
    cache.set(TOKEN_CACHE_KEY, "vieux", 60)
    http.add("GET", "/v1/payment/GC27-12-1", 401, {"code": 1003, "status": "EXPIRED_TOKEN"})
    http.add("POST", "/v1/oauth/login", 200, {"access_token": "neuf"})
    http.add(
        "GET",
        "/v1/payment/GC27-12-1",
        200,
        {"code": 100, "status": "SUCCESS", "merchant_transaction_id": "GC27-12-1"},
    )
    check = CinetPayProvider().check(payment())
    assert (check.outcome, check.provider_status) == ("succeeded", "SUCCESS")
    assert http.calls[-1]["headers"]["Authorization"] == "Bearer neuf"


@pytest.mark.parametrize(
    ("status", "body", "outcome"),
    [
        (200, {"status": "PENDING"}, "pending"),
        (200, {"status": "INITIATED"}, "pending"),
        (404, {"code": 404, "status": "NOT_FOUND"}, "pending"),
        (200, {"code": 2010, "status": "FAILED"}, "failed"),
        (200, {"status": "EXPIRED"}, "failed"),
    ],
)
def test_status_mapping(http, status, body, outcome):
    cache.set(TOKEN_CACHE_KEY, "jwt", 60)
    http.add("GET", "/v1/payment/GC27-12-1", status, body)
    assert CinetPayProvider().check(payment()).outcome == outcome


def test_success_for_another_reference_is_refused(http):
    cache.set(TOKEN_CACHE_KEY, "jwt", 60)
    http.add(
        "GET",
        "/v1/payment/GC27-12-1",
        200,
        {"status": "SUCCESS", "merchant_transaction_id": "GC27-99-1"},
    )
    with pytest.raises(ProviderError):
        CinetPayProvider().check(payment())


def test_network_failure_and_refused_login_are_provider_errors(http, monkeypatch):
    http.add("POST", "/v1/oauth/login", 401, {"code": 1005, "status": "INVALID_CREDENTIALS"})
    with pytest.raises(ProviderError) as error:
        initiate(CinetPayProvider())
    assert "mot-de-passe" not in str(error.value)

    def down(*args, **kwargs):
        raise requests.ConnectionError("dns")

    monkeypatch.setattr(requests, "request", down)
    with pytest.raises(ProviderError):
        CinetPayProvider().check(payment())


def test_urls_longer_than_120_characters_are_refused(http):
    with pytest.raises(ProviderError):
        initiate(CinetPayProvider(), success="https://c.test/" + "x" * 120)


def test_supported_currencies_and_amounts():
    provider = CinetPayProvider()
    assert provider.supports("XOF", Decimal("25000")) is None
    assert provider.supports("EUR", Decimal("100")) is not None
    assert provider.supports("XOF", Decimal("99")) is not None
    assert provider.supports("XOF", Decimal("2500001")) is not None
    assert provider.supports("USD", Decimal("100.50")) is not None


def test_notification_whitelist_never_keeps_token_or_payer():
    notification = CinetPayProvider().parse_notification(
        {
            "notify_token": "nt-secret",
            "merchant_transaction_id": "GC27-12-1",
            "transaction_id": "CP-1",
            "user": {"name": "Awa Zadi", "email": "awa@example.org", "phone_number": "+225"},
        }
    )
    assert notification.token == "nt-secret"
    assert notification.fields == {"merchant_transaction_id": "GC27-12-1", "transaction_id": "CP-1"}
    with pytest.raises(InvalidNotification):
        CinetPayProvider().parse_notification({"transaction_id": "CP-1"})
