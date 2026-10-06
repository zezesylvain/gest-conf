"""Montants et devises (plan L6, J2) : décimales ISO 4217, arrondi, affichage."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.money import (
    MINUS,
    NARROW_NBSP,
    NBSP,
    format_amount,
    is_exact,
    minor_units,
    quantize,
)


def test_iso_4217_minor_units():
    """Bilan de L6.0 : XOF, XAF, GNF sans décimale ; EUR, USD, CDF à deux décimales."""
    assert {code: minor_units(code) for code in ("XOF", "XAF", "GNF", "EUR", "USD", "CDF")} == {
        "XOF": 0,
        "XAF": 0,
        "GNF": 0,
        "EUR": 2,
        "USD": 2,
        "CDF": 2,
    }


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("2500.5", "XOF", "2501"),
        ("2500.49", "XOF", "2500"),
        ("10.005", "EUR", "10.01"),
        ("10.004", "EUR", "10.00"),
    ],
)
def test_quantize_half_up_to_currency_decimals(amount, currency, expected):
    assert quantize(Decimal(amount), currency) == Decimal(expected)


def test_is_exact():
    assert is_exact(Decimal("25000.00"), "XOF")
    assert not is_exact(Decimal("12.50"), "XOF")
    assert is_exact(Decimal("12.50"), "EUR")
    assert not is_exact(Decimal("12.505"), "EUR")


def test_format_amount_french_and_english():
    """Français : espace fine insécable entre milliers, insécable avant le symbole, vrai
    signe moins ; anglais : virgule et symbole en tête."""
    thin, space = NARROW_NBSP, NBSP
    assert format_amount(Decimal("25000"), "XOF") == f"25{thin}000{space}F CFA"
    assert format_amount(Decimal("1234.5"), "EUR") == f"1{thin}234,50{space}€"
    assert format_amount(Decimal("-3500"), "XOF") == f"{MINUS}3{thin}500{space}F CFA"
    assert format_amount(Decimal("999"), "XOF") == f"999{space}F CFA"
    assert format_amount(Decimal("25000"), "XOF", "en") == "F CFA 25,000"
    assert format_amount(Decimal("1234.5"), "EUR", "en") == "€1,234.50"
