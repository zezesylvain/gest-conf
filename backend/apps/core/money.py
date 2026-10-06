"""Montants et devises (plan L6, J2 ; bilan de L6.0).

Un montant est un ``Decimal`` dans la devise de l'édition, jamais un flottant. Les
décimales suivent **ISO 4217** (liste publiée le 1er janvier 2026, vérifiée en L6.0) :
table fermée, sans dépendance. Pas de conversion entre devises.

Arrondi : au demi supérieur, à la décimale de la devise, une seule fois par ligne calculée
(remise en pourcentage) ; les totaux sont des sommes de lignes déjà arrondies.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _

# Chiffres significatifs des colonnes de montant : 10 avant la virgule, 2 après.
MAX_DIGITS = 12
DECIMAL_PLACES = 2


class Currency(models.TextChoices):
    """Devises proposées pour une édition : franc CFA (UEMOA et CEMAC), devises de CinetPay
    (franc guinéen, franc congolais, dollar) et euro (paiement manuel seulement en L6)."""

    XOF = "XOF", _("franc CFA (UEMOA)")
    XAF = "XAF", _("franc CFA (CEMAC)")
    EUR = "EUR", _("euro")
    USD = "USD", _("dollar des États-Unis")
    GNF = "GNF", _("franc guinéen")
    CDF = "CDF", _("franc congolais")


# Décimales ISO 4217 (« minor units »).
MINOR_UNITS: dict[str, int] = {
    Currency.XOF: 0,
    Currency.XAF: 0,
    Currency.EUR: 2,
    Currency.USD: 2,
    Currency.GNF: 0,
    Currency.CDF: 2,
}

# Symboles d'affichage des PDF et des e-mails (le navigateur utilise Intl.NumberFormat).
SYMBOLS: dict[str, str] = {
    Currency.XOF: "F CFA",
    Currency.XAF: "FCFA",
    Currency.EUR: "€",
    Currency.USD: "$",
    Currency.GNF: "FG",
    Currency.CDF: "FC",
}

NARROW_NBSP = "\u202f"
NBSP = "\u00a0"
MINUS = "\u2212"


def minor_units(currency: str) -> int:
    return MINOR_UNITS[currency]


def quantum(currency: str) -> Decimal:
    return Decimal(1).scaleb(-minor_units(currency))


def quantize(amount: Decimal, currency: str) -> Decimal:
    """Arrondi au demi supérieur à la décimale de la devise."""
    return amount.quantize(quantum(currency), rounding=ROUND_HALF_UP)


def is_exact(amount: Decimal, currency: str) -> bool:
    """Vrai si ``amount`` n'a pas plus de décimales que la devise (25 000 XOF, 12,50 EUR)."""
    return amount == amount.quantize(quantum(currency))


def format_amount(amount: Decimal, currency: str, language: str = "fr") -> str:
    """« 25 000 F CFA », « 1 234,50 € » (français) ; « F CFA 25,000 », « €1,234.50 »
    (anglais). Séparateur des milliers : espace fine insécable en français."""
    value = quantize(amount, currency)
    sign = MINUS if value < 0 else ""
    integer, _sep, fraction = f"{abs(value):f}".partition(".")
    groups: list[str] = []
    while integer:
        groups.insert(0, integer[-3:])
        integer = integer[:-3]
    symbol = SYMBOLS.get(currency, currency)
    if language == "en":
        number = ",".join(groups) + (f".{fraction}" if fraction else "")
        joiner = "" if symbol in {"€", "$"} else " "
        return f"{sign}{symbol}{joiner}{number}"
    number = NARROW_NBSP.join(groups) + (f",{fraction}" if fraction else "")
    return f"{sign}{number}{NBSP}{symbol}"
