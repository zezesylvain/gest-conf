"""Fournisseur factice (plan L6, J6) : démonstration, E2E et tests. Refusé en production sauf
recette déclarée (``config/settings/prod.py``).

Sa « page hébergée » est ``/v1/payments/fake/{référence}`` (``views.FakeCheckoutView``) :
payer ou refuser y fixe le statut côté « fournisseur » (cache de la base), puis envoie la
notification comme le ferait un agrégateur, et renvoie le navigateur au portail.
"""

from __future__ import annotations

import secrets
from decimal import Decimal

from django.conf import settings
from django.core.cache import cache

from apps.payments.providers.base import (
    Customer,
    Initiation,
    InvalidNotification,
    Notification,
    StatusCheck,
)

STATE_TTL = 7 * 24 * 3600


def _key(reference: str) -> str:
    return f"payments:fake:{reference}"


def set_state(reference: str, **values) -> None:
    state = cache.get(_key(reference)) or {}
    state.update(values)
    cache.set(_key(reference), state, STATE_TTL)


def get_state(reference: str) -> dict:
    return cache.get(_key(reference)) or {}


class FakeProvider:
    name = "fake"

    def supports(self, currency: str, amount: Decimal) -> str | None:
        return None if amount > 0 else "montant nul"

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
        token = secrets.token_urlsafe(24)
        transaction_id = f"FAKE-{secrets.token_hex(6)}"
        set_state(
            payment.reference,
            status="INITIATED",
            transaction_id=transaction_id,
            token=token,
            amount=str(payment.amount),
            currency=payment.currency,
            success_url=success_url,
            failed_url=failed_url,
        )
        url = f"{settings.GESTCONF_PUBLIC_URL}/api/v1/payments/fake/{payment.reference}"
        return Initiation(payment_url=url, provider_reference=transaction_id, notify_token=token)

    def parse_notification(self, data: dict) -> Notification:
        reference = str(data.get("merchant_transaction_id") or "")
        token = str(data.get("notify_token") or "")
        if not reference or not token:
            raise InvalidNotification("merchant_transaction_id ou notify_token absent")
        return Notification(
            reference=reference,
            provider_reference=str(data.get("transaction_id") or ""),
            token=token,
            fields={"merchant_transaction_id": reference},
        )

    def check(self, payment) -> StatusCheck:
        state = get_state(payment.reference)
        status = state.get("status", "NOT_FOUND")
        outcome = {"SUCCESS": "succeeded", "FAILED": "failed"}.get(status, "pending")
        amount = state.get("amount")
        return StatusCheck(
            outcome=outcome,
            provider_status=status,
            provider_reference=state.get("transaction_id", ""),
            amount=Decimal(amount) if amount else None,
            currency=state.get("currency"),
        )
