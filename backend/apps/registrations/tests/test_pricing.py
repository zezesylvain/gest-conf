"""Tarification (plan L6, J2 à J4) : périodes, calcul du prix, remises, réservations."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.db import connection, transaction

from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.registrations.models import Period, PromoCode, RegistrationOption
from apps.registrations.services import pricing
from apps.registrations.services.pricing import RegistrationWindow, period_at, quote
from apps.registrations.services.settings import registration_settings
from apps.registrations.tests.helpers import NOW, grid, open_edition, option, set_window

pytestmark = pytest.mark.django_db

DAY = dt.timedelta(days=1)


@pytest.fixture
def edition():
    edition = EditionFactory(country="CI")
    set_window(edition, opens=NOW - 10 * DAY, early=NOW + 10 * DAY, closes=NOW + 40 * DAY)
    return edition


@pytest.fixture
def student(edition):
    return grid(
        edition,
        early_local="25000",
        early_international="50000",
        regular_local="35000",
        regular_international="60000",
        onsite_local="45000",
    )


# --- Périodes (J2) -------------------------------------------------------------------------


def test_j2_periods_follow_key_dates():
    window = RegistrationWindow(opens_at=NOW, early_bird_end=NOW + DAY, closes_at=NOW + 2 * DAY)
    assert period_at(window, NOW - dt.timedelta(seconds=1)) is None
    assert period_at(window, NOW) == Period.EARLY
    assert period_at(window, NOW + DAY) == Period.REGULAR
    assert period_at(window, NOW + 2 * DAY) == Period.ONSITE


def test_j2_without_early_bird_or_closing_date():
    assert period_at(RegistrationWindow(NOW, None, None), NOW + 100 * DAY) == Period.REGULAR
    # Sans date d'ouverture, les inscriptions ne sont pas ouvertes.
    assert period_at(RegistrationWindow(None, None, None), NOW) is None


def test_j2_open_online_only_for_published_edition_before_closing():
    edition = open_edition()
    assert pricing.is_open_online(edition)
    edition.status = EditionStatus.DRAFT
    assert not pricing.is_open_online(edition)
    edition.status = EditionStatus.PUBLISHED
    window = pricing.registration_window(edition)
    assert not pricing.is_open_online(edition, at=window.closes_at)


# --- Prix (J2) ----------------------------------------------------------------------------


def test_j2_fee_by_period_and_zone(edition, student):
    assert quote(edition, category="etudiant", country="CI", at=NOW).total == Decimal("25000")
    assert quote(edition, category="etudiant", country="FR", at=NOW).total == Decimal("50000")
    later = NOW + 20 * DAY
    found = quote(edition, category="etudiant", country="CI", at=later)
    assert (found.period, found.zone, found.total) == ("regular", "local", Decimal("35000"))


def test_j2_local_countries_from_settings(edition, student):
    settings = registration_settings(edition)
    settings.local_countries = ["SN"]
    settings.save()
    assert quote(edition, category="etudiant", country="SN", at=NOW).zone == "local"
    assert quote(edition, category="etudiant", country="CI", at=NOW).zone == "international"


def test_j2_missing_fee_means_category_not_offered(edition, student):
    """Pas de tarif « sur place, international » : combinaison non proposée."""
    with pytest.raises(Invalid) as error:
        quote(edition, category="etudiant", country="FR", period=Period.ONSITE, at=NOW)
    assert "category" in error.value.fields


def test_j2_zero_fee_is_free(edition):
    grid(edition, "invite", early_local="0")
    assert quote(edition, category="invite", country="CI", at=NOW).total == Decimal("0")


def test_unknown_or_inactive_category(edition, student):
    student.is_active = False
    student.save()
    with pytest.raises(Invalid):
        quote(edition, category="etudiant", country="CI", at=NOW)
    with pytest.raises(Invalid):
        quote(edition, category="inconnue", country="CI", at=NOW)


def test_closed_before_opening(edition, student):
    with pytest.raises(RuleViolation) as error:
        quote(edition, category="etudiant", country="CI", at=NOW - 20 * DAY)
    assert error.value.code == ErrorCode.REGISTRATION_CLOSED


def test_lines_frozen_with_codes_and_labels(edition, student):
    option(edition, "diner", label_fr="Dîner de gala", label_en="Gala dinner")
    found = quote(edition, category="etudiant", options=["diner"], country="CI", at=NOW)
    assert [line.as_json() for line in found.lines] == [
        {
            "kind": "registration",
            "code": "etudiant",
            "label_fr": "Etudiant",
            "label_en": "etudiant (EN)",
            "amount": "25000.00",
        },
        {
            "kind": "option",
            "code": "diner",
            "label_fr": "Dîner de gala",
            "label_en": "Gala dinner",
            "amount": "10000.00",
        },
    ]
    assert found.total == Decimal("35000")


# --- Options (J3) ---------------------------------------------------------------------------


def test_j3_option_price_by_zone(edition, student):
    option(edition, "atelier", price_local=Decimal("5000"), price_international=Decimal("8000"))
    local = quote(edition, category="etudiant", options=["atelier"], country="CI", at=NOW)
    abroad = quote(edition, category="etudiant", options=["atelier"], country="FR", at=NOW)
    assert (local.total, abroad.total) == (Decimal("30000"), Decimal("58000"))


def test_j3_option_restricted_to_categories(edition, student):
    other = grid(edition, "participant", early_local="40000")
    workshop = option(edition, "atelier")
    workshop.categories.set([other])
    with pytest.raises(Invalid) as error:
        quote(edition, category="etudiant", options=["atelier"], country="CI", at=NOW)
    assert "options" in error.value.fields
    assert quote(edition, category="participant", options=["atelier"], country="CI", at=NOW)


def test_j3_unknown_inactive_or_duplicate_option(edition, student):
    option(edition, "visite", is_active=False)
    for chosen in (["visite"], ["absente"]):
        with pytest.raises(Invalid):
            quote(edition, category="etudiant", options=chosen, country="CI", at=NOW)
    option(edition, "diner")
    with pytest.raises(Invalid):
        quote(edition, category="etudiant", options=["diner", "diner"], country="CI", at=NOW)


# --- Codes promo (J4) -----------------------------------------------------------------------


def promo(edition, code="ETU10", kind="percent", value="10", **fields) -> PromoCode:
    return PromoCode.objects.create(
        edition=edition, code=code, kind=kind, value=Decimal(value), **fields
    )


def test_j4_percent_rounded_half_up_once_on_registration_only(edition):
    """10 % de 25 005 F CFA = 2 500,5 → 2 501 (XOF sans décimale, demi supérieur)."""
    grid(edition, "odd", early_local="25005")
    option(edition, "diner")
    promo(edition)
    found = quote(
        edition, category="odd", options=["diner"], promo_code="etu10", country="CI", at=NOW
    )
    assert found.lines[-1].as_json()["amount"] == "-2501"
    assert found.lines[-1].label_fr == "Remise ETU10"
    assert found.total == Decimal("25005") + Decimal("10000") - Decimal("2501")


def test_j4_scope_all_includes_options(edition, student):
    option(edition, "diner")
    promo(edition, scope="all", value="50")
    found = quote(
        edition, category="etudiant", options=["diner"], promo_code="ETU10", country="CI", at=NOW
    )
    assert found.total == Decimal("17500")


def test_j4_amount_discount_never_exceeds_base(edition, student):
    promo(edition, code="GRATUIT", kind="amount", value="100000")
    found = quote(edition, category="etudiant", promo_code="GRATUIT", country="CI", at=NOW)
    assert found.total == Decimal("0")
    assert found.lines[-1].amount == Decimal("-25000")


def test_j4_expired_inactive_or_unknown_code_is_refused(edition, student):
    promo(edition, code="VIEUX", valid_until=NOW - DAY)
    promo(edition, code="OFF", is_active=False)
    for code in ("VIEUX", "OFF", "ABSENT"):
        with pytest.raises(Invalid) as error:
            quote(edition, category="etudiant", promo_code=code, country="CI", at=NOW)
        assert "promo_code" in error.value.fields


def test_j4_code_restricted_to_categories(edition, student):
    other = grid(edition, "participant", early_local="40000")
    restricted = promo(edition)
    restricted.categories.set([other])
    with pytest.raises(Invalid):
        quote(edition, category="etudiant", promo_code="ETU10", country="CI", at=NOW)


def test_j4_exhausted_code(edition, student):
    promo(edition, max_uses=2, reserved_uses=1, consumed_uses=1)
    with pytest.raises(RuleViolation) as error:
        quote(edition, category="etudiant", promo_code="ETU10", country="CI", at=NOW)
    assert error.value.code == ErrorCode.PROMO_CODE_EXHAUSTED


# --- Réservations (J3, J4) ------------------------------------------------------------------


def test_j3_quota_reserved_then_full_then_released(edition):
    dinner = option(edition, quota=1)
    with transaction.atomic():
        pricing.reserve_options([dinner])
    with pytest.raises(RuleViolation) as error, transaction.atomic():
        pricing.reserve_options([dinner])
    assert error.value.code == ErrorCode.OPTION_FULL
    with transaction.atomic():
        pricing.release_options([dinner])
    dinner.refresh_from_db()
    assert dinner.reserved == 0


def test_j4_promo_reserved_consumed_and_released(edition):
    code = promo(edition, max_uses=2)
    with transaction.atomic():
        pricing.reserve_promo(code)
        pricing.reserve_promo(code)
    with pytest.raises(RuleViolation), transaction.atomic():
        pricing.reserve_promo(code)
    with transaction.atomic():
        pricing.consume_promo(code)
        pricing.release_promo(code)
    code.refresh_from_db()
    assert (code.reserved_uses, code.consumed_uses) == (0, 1)


@pytest.mark.django_db(transaction=True)
def test_reservations_require_a_transaction():
    """Hors transaction, le verrou de ligne ne tiendrait pas jusqu'à la fin de la commande."""
    with pytest.raises(RuntimeError):
        pricing.reserve_options([option(EditionFactory())])


@pytest.mark.mariadb_only  # SQLite verrouille la base entière : sans objet
@pytest.mark.django_db(transaction=True)
def test_j3_last_place_reserved_once_under_concurrency():
    """Deux commandes simultanées pour la dernière place : une seule l'obtient."""
    import threading

    current = EditionFactory()
    last = option(current, quota=1)
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def reserve() -> None:
        try:
            barrier.wait(5)
            with transaction.atomic():
                pricing.reserve_options([last])
            outcomes.append("ok")
        except RuleViolation as error:
            outcomes.append(error.code)
        finally:
            connection.close()

    threads = [threading.Thread(target=reserve) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert sorted(outcomes) == ["ok", ErrorCode.OPTION_FULL]
    assert RegistrationOption.objects.get(pk=last.pk).reserved == 1
