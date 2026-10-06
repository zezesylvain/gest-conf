"""Interface d'un fournisseur de paiement en ligne (plan L6, J6 ; RG-15).

Un fournisseur **initie** un paiement sur sa page hébergée (aucune donnée de carte chez nous,
règle n° 7), **lit** une notification et **interroge** le statut d'un paiement. La décision
de confirmer ne vient que de l'interrogation (``check``), jamais du contenu d'une
notification ni du retour du navigateur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from apps.payments.models import Payment


class ProviderError(Exception):
    """Fournisseur injoignable ou réponse inexploitable (réseau, délai, erreur d'API)."""


class InvalidNotification(Exception):
    """Notification illisible : champs obligatoires absents."""


@dataclass(frozen=True, slots=True)
class Customer:
    first_name: str
    last_name: str
    email: str


@dataclass(frozen=True, slots=True)
class Initiation:
    payment_url: str
    provider_reference: str
    notify_token: str


@dataclass(frozen=True, slots=True)
class Notification:
    """Ce qu'annonce une notification. ``token`` n'est jamais conservé ; ``fields`` : champs
    en liste blanche, journalisés."""

    reference: str
    provider_reference: str
    token: str
    fields: dict = field(default_factory=dict)


Outcome = Literal["succeeded", "failed", "pending"]


@dataclass(frozen=True, slots=True)
class StatusCheck:
    """Statut interrogé côté serveur. ``amount`` et ``currency`` : ``None`` si le fournisseur
    ne les renvoie pas (CinetPay v1 : le montant est lié à la référence à l'initiation)."""

    outcome: Outcome
    provider_status: str
    provider_reference: str = ""
    amount: Decimal | None = None
    currency: str | None = None


class PaymentProvider(Protocol):
    name: str

    def supports(self, currency: str, amount: Decimal) -> str | None:
        """``None`` si le paiement est possible, sinon la raison (devise, montant)."""

    def initiate(
        self,
        payment: Payment,
        *,
        customer: Customer,
        designation: str,
        language: str,
        success_url: str,
        failed_url: str,
        notify_url: str,
    ) -> Initiation: ...

    def parse_notification(self, data: dict) -> Notification: ...

    def check(self, payment: Payment) -> StatusCheck: ...
