"""CinetPay, API v1 (plan L6, J6 ; bilan de L6.0), écrit sur ``requests`` d'après le SDK
Python officiel ``cinetpay-python`` 0.1.0 (lu, non installé).

- Jeton : ``POST /v1/oauth/login`` (``api_key``, ``api_password``), valable 24 h, gardé
  23 h dans le cache de la base (partagé entre processus Passenger et cron), jamais
  journalisé ; renouvelé une fois sur ``EXPIRED_TOKEN`` ou ``INVALID_TOKEN``.
- Initiation : ``POST /v1/payment`` → ``payment_url``, ``notify_token``, ``transaction_id``.
- Notification : ``notify_token``, ``transaction_id``, ``merchant_transaction_id`` (JSON ou
  formulaire) ; aucun statut n'y est cru.
- Statut : ``GET /v1/payment/{merchant_transaction_id}`` → ``status``.

Contraintes du SDK : devises XOF, XAF, GNF, CDF, USD ; montant entier de 100 à 2 500 000 ;
référence de 30 caractères au plus ; adresses de retour de 120 caractères au plus.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from apps.payments.providers.base import (
    Customer,
    Initiation,
    InvalidNotification,
    Notification,
    ProviderError,
    StatusCheck,
)

SANDBOX_URL = "https://api.cinetpay.net"
PRODUCTION_URL = "https://api.cinetpay.co"
TOKEN_CACHE_KEY = "payments:cinetpay:token"  # noqa: S105 (clé de cache, pas un secret)
TOKEN_TTL_SECONDS = 23 * 3600
CURRENCIES = frozenset({"XOF", "XAF", "GNF", "CDF", "USD"})
MIN_AMOUNT, MAX_AMOUNT = 100, 2_500_000
URL_MAX = 120
EXPIRED_TOKEN_CODES = frozenset({1002, 1003})
EXPIRED_TOKEN_STATUSES = frozenset({"EXPIRED_TOKEN", "INVALID_TOKEN"})
FAILED_STATUSES = frozenset(
    {"FAILED", "EXPIRED", "INSUFFICIENT_BALANCE", "USER_IS_BLOCKED", "NOT_ALLOWED", "OTP_EXPIRED"}
)


def _name(value: str) -> str:
    """Nom et prénom : 2 à 255 caractères exigés par l'API."""
    value = value.strip()[:255]
    return value if len(value) >= 2 else (value + "--")[:2] if value else "--"


class CinetPayProvider:
    name = "cinetpay"

    def __init__(self) -> None:
        self.base_url = SANDBOX_URL if settings.CINETPAY_SANDBOX else PRODUCTION_URL
        self.timeout = settings.CINETPAY_TIMEOUT_SECONDS

    # --- HTTP ------------------------------------------------------------------------------

    def _call(self, method: str, path: str, *, body: dict | None = None, token: str | None):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = requests.request(
                method,
                f"{self.base_url}{path}",
                json=body,
                headers=headers,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise ProviderError(f"{method} {path} : réseau ({type(exc).__name__})") from None
        try:
            data: dict[str, Any] = response.json()
        except ValueError:
            message = f"{method} {path} : réponse non JSON ({response.status_code})"
            raise ProviderError(message) from None
        return response.status_code, data

    def _token(self, *, refresh: bool = False) -> str:
        if not refresh:
            cached = cache.get(TOKEN_CACHE_KEY)
            if cached:
                return cached
        status, data = self._call(
            "POST",
            "/v1/oauth/login",
            body={
                "api_key": settings.CINETPAY_API_KEY,
                "api_password": settings.CINETPAY_API_PASSWORD,
            },
            token=None,
        )
        token = data.get("access_token")
        if status >= 400 or not token:
            raise ProviderError(f"authentification refusée ({status}, {data.get('status')})")
        cache.set(TOKEN_CACHE_KEY, token, TOKEN_TTL_SECONDS)
        return token

    def _authorized(self, method: str, path: str, body: dict | None = None):
        status, data = self._call(method, path, body=body, token=self._token())
        if data.get("code") in EXPIRED_TOKEN_CODES or data.get("status") in EXPIRED_TOKEN_STATUSES:
            status, data = self._call(method, path, body=body, token=self._token(refresh=True))
        return status, data

    # --- Interface ---------------------------------------------------------------------------

    def supports(self, currency: str, amount: Decimal) -> str | None:
        if currency not in CURRENCIES:
            return f"devise {currency} non prise en charge par CinetPay"
        if amount != amount.to_integral_value():
            return "montant non entier"
        if not MIN_AMOUNT <= amount <= MAX_AMOUNT:
            return f"montant hors de {MIN_AMOUNT} à {MAX_AMOUNT}"
        return None

    def initiate(
        self,
        payment,
        *,
        customer: Customer,
        designation: str,
        language: str,
        success_url: str,
        failed_url: str,
        notify_url: str,
    ) -> Initiation:
        for url in (success_url, failed_url, notify_url):
            if len(url) > URL_MAX:
                raise ProviderError(f"adresse de plus de {URL_MAX} caractères : {url[:40]}…")
        body = {
            "currency": payment.currency,
            "merchant_transaction_id": payment.reference,
            "amount": int(payment.amount),
            "lang": "en" if language == "en" else "fr",
            "designation": designation[:255],
            "client_email": customer.email,
            "client_first_name": _name(customer.first_name),
            "client_last_name": _name(customer.last_name),
            "success_url": success_url,
            "failed_url": failed_url,
            "notify_url": notify_url,
            "channel": "PUSH",
        }
        status, data = self._authorized("POST", "/v1/payment", body)
        url, token = data.get("payment_url"), data.get("notify_token")
        if status >= 400 or not url or not token:
            raise ProviderError(f"initiation refusée ({status}, {data.get('status')})")
        return Initiation(
            payment_url=str(url),
            provider_reference=str(data.get("transaction_id") or ""),
            notify_token=str(token),
        )

    def parse_notification(self, data: dict) -> Notification:
        token = str(data.get("notify_token") or "")
        reference = str(data.get("merchant_transaction_id") or "")
        transaction_id = str(data.get("transaction_id") or "")
        if not token or not reference:
            raise InvalidNotification("notify_token ou merchant_transaction_id absent")
        # Liste blanche : ni le jeton ni l'identité du payeur (``user``) ne sont conservés.
        return Notification(
            reference=reference,
            provider_reference=transaction_id,
            token=token,
            fields={"merchant_transaction_id": reference, "transaction_id": transaction_id},
        )

    def check(self, payment) -> StatusCheck:
        status, data = self._authorized("GET", f"/v1/payment/{payment.reference}")
        provider_status = str(data.get("status") or "")
        if provider_status == "SUCCESS":
            outcome = "succeeded"
        elif provider_status in FAILED_STATUSES:
            outcome = "failed"
        elif status >= 500 or not provider_status:
            raise ProviderError(f"statut illisible ({status})")
        else:  # INITIATED, PENDING, NOT_FOUND (jamais payé) : rien de définitif
            outcome = "pending"
        reference = str(data.get("merchant_transaction_id") or "")
        if outcome == "succeeded" and reference != payment.reference:
            raise ProviderError("référence de la réponse différente de celle interrogée")
        return StatusCheck(
            outcome=outcome,
            provider_status=provider_status,
            provider_reference=str(data.get("transaction_id") or ""),
        )
