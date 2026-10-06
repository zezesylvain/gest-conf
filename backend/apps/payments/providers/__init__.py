"""Fournisseurs de paiement en ligne (plan L6, J6) : interface commune, fournisseur factice
(démonstration et tests), CinetPay (API v1, bilan de L6.0)."""

from __future__ import annotations

from django.conf import settings

from apps.payments.providers.base import PaymentProvider


def get_provider(name: str) -> PaymentProvider | None:
    if name == "fake":
        from apps.payments.providers.fake import FakeProvider

        return FakeProvider()
    if name == "cinetpay":
        from apps.payments.providers.cinetpay import CinetPayProvider

        return CinetPayProvider()
    return None


def online_provider() -> PaymentProvider | None:
    """Fournisseur configuré (``GESTCONF_PAYMENT_PROVIDER``), ou ``None`` : paiement manuel
    seul."""
    return get_provider(settings.GESTCONF_PAYMENT_PROVIDER)
