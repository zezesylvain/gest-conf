"""Catalogue des inscriptions dans la gestion (plan L6, J2 à J4) : catégories, grilles de
tarifs, options à quota, codes promo."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog
from apps.registrations.models import Fee, PromoCode, RegistrationOption
from apps.registrations.tests.factories import make_registration
from apps.registrations.tests.helpers import grid, option

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def finance(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))


def base(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/registrations"


# --- Catégories et tarifs (J2) ----------------------------------------------------------------


def test_j2_category_created_with_its_fee_grid(edition, finance):
    response = finance.post(
        f"{base(edition)}/categories",
        {"code": "etudiant", "label_fr": "Étudiant", "label_en": "Student", "requires_proof": True},
        format="json",
    )
    assert response.status_code == 201, response.content
    category_id = response.json()["id"]
    response = finance.put(
        f"{base(edition)}/categories/{category_id}/fees",
        {
            "fees": [
                {"period": "regular", "zone": "local", "amount": "35000"},
                {"period": "early", "zone": "local", "amount": "25000"},
                {"period": "early", "zone": "international", "amount": "50000"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["fees"] == [
        {"period": "early", "zone": "international", "amount": "50000.00"},
        {"period": "early", "zone": "local", "amount": "25000.00"},
        {"period": "regular", "zone": "local", "amount": "35000.00"},
    ]
    log = AuditLog.objects.get(action="registrations.fees_changed")
    assert log.before == {}
    assert log.after["early:local"] == "25000.00"
    # Grille remplacée : la cellule absente disparaît.
    finance.put(
        f"{base(edition)}/categories/{category_id}/fees",
        {"fees": [{"period": "early", "zone": "local", "amount": "20000"}]},
        format="json",
    )
    assert list(Fee.objects.values_list("period", "zone", "amount")) == [
        ("early", "local", Decimal("20000.00"))
    ]


@pytest.mark.parametrize("amount", ["-1", "25000.50"])
def test_j2_fee_positive_and_exact_in_xof(edition, finance, amount):
    category = grid(edition)
    response = finance.put(
        f"{base(edition)}/categories/{category.pk}/fees",
        {"fees": [{"period": "early", "zone": "local", "amount": amount}]},
        format="json",
    )
    assert response.status_code == 400
    assert "fees" in response.json()["fields"]


def test_j2_duplicate_cell_refused(edition, finance):
    category = grid(edition)
    cell = {"period": "early", "zone": "local", "amount": "1000"}
    response = finance.put(
        f"{base(edition)}/categories/{category.pk}/fees", {"fees": [cell, cell]}, format="json"
    )
    assert response.status_code == 400


def test_category_code_fixed_after_creation(edition, finance):
    category = grid(edition)
    url = f"{base(edition)}/categories/{category.pk}"
    response = finance.patch(url, {"code": "autre"}, format="json")
    assert response.status_code == 400
    assert "code" in response.json()["fields"]
    response = finance.patch(url, {"label_fr": "Étudiant·e", "is_active": False}, format="json")
    assert response.status_code == 200
    assert (response.json()["label_fr"], response.json()["is_active"]) == ("Étudiant·e", False)


def test_category_code_unique_per_edition(edition, finance):
    grid(edition, "etudiant")
    response = finance.post(
        f"{base(edition)}/categories", {"code": "etudiant", "label_fr": "Bis"}, format="json"
    )
    assert response.status_code == 400


def test_used_category_cannot_be_deleted_only_deactivated(edition, finance):
    category = grid(edition, early_local="1000")
    make_registration(edition, VerifiedUserFactory(), category=category)
    response = finance.delete(f"{base(edition)}/categories/{category.pk}")
    assert response.status_code == 409
    assert response.json()["code"] == "in_use"
    listed = finance.get(f"{base(edition)}/categories").json()
    assert listed[0]["in_use"] is True
    unused = grid(edition, "libre", early_local="1000")
    assert finance.delete(f"{base(edition)}/categories/{unused.pk}").status_code == 204
    assert not Fee.objects.filter(category_id=unused.pk).exists()


def test_category_of_another_edition_is_404(edition, finance):
    other = grid(EditionFactory())
    assert finance.patch(f"{base(edition)}/categories/{other.pk}", {}).status_code == 404


# --- Options (J3) ---------------------------------------------------------------------------


def test_j3_option_with_quota_and_categories(edition, finance):
    grid(edition, "etudiant")
    response = finance.post(
        f"{base(edition)}/options",
        {
            "code": "atelier",
            "label_fr": "Atelier",
            "price_local": "5000",
            "price_international": "8000",
            "quota": 30,
            "categories": ["etudiant"],
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["quota"], body["reserved"], body["categories"]) == (30, 0, ["etudiant"])


def test_j3_option_categories_of_another_edition_refused(edition, finance):
    grid(EditionFactory(), "ailleurs")
    response = finance.post(
        f"{base(edition)}/options",
        {"code": "atelier", "label_fr": "Atelier", "categories": ["ailleurs"]},
        format="json",
    )
    assert response.status_code == 400
    assert "categories" in response.json()["fields"]


def test_j3_quota_never_below_reserved_places(edition, finance):
    dinner = option(edition, quota=10, reserved=4)
    url = f"{base(edition)}/options/{dinner.pk}"
    assert finance.patch(url, {"quota": 3}, format="json").status_code == 400
    assert finance.patch(url, {"quota": 4}, format="json").status_code == 200
    assert finance.patch(url, {"quota": None}, format="json").json()["quota"] is None


def test_j3_reserved_option_cannot_be_deleted(edition, finance):
    dinner = option(edition, reserved=1)
    assert finance.delete(f"{base(edition)}/options/{dinner.pk}").status_code == 409
    RegistrationOption.objects.filter(pk=dinner.pk).update(reserved=0)
    assert finance.delete(f"{base(edition)}/options/{dinner.pk}").status_code == 204


# --- Codes promo (J4) -------------------------------------------------------------------------


def test_d13_promo_code_deadline_entered_in_edition_local_time():
    """D13 : « valable jusqu'au » saisi à l'heure de l'édition, stocké en UTC."""
    edition = EditionFactory(timezone="Europe/Paris")
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))
    response = client.post(
        f"{base(edition)}/promo-codes",
        {"code": "ete", "kind": "percent", "value": "10", "valid_until_local": "2027-07-01T23:59"},
        format="json",
    )
    assert response.status_code == 201, response.content
    assert response.json()["valid_until"] == "2027-07-01T21:59:00Z"
    assert response.json()["valid_until_local"] == "2027-07-01T23:59:00"
    promo = PromoCode.objects.get(edition=edition)
    response = client.patch(
        f"{base(edition)}/promo-codes/{promo.pk}",
        {"valid_until_local": "2027-10-31T02:30"},
        format="json",
    )
    assert response.status_code == 400, "heure ambiguë (retour à l'heure d'hiver)"
    assert list(response.json()["fields"]) == ["valid_until_local"]


def test_j4_promo_code_normalized_and_unique_ignoring_case(edition, finance):
    url = f"{base(edition)}/promo-codes"
    response = finance.post(url, {"code": " etu10 ", "kind": "percent", "value": "10"})
    assert response.status_code == 201, response.content
    assert response.json()["code"] == "ETU10"
    duplicate = finance.post(url, {"code": "Etu10", "kind": "amount", "value": "1000"})
    assert duplicate.status_code == 400
    assert "code" in duplicate.json()["fields"]


@pytest.mark.parametrize(
    ("kind", "value"), [("percent", "101"), ("percent", "0"), ("amount", "99.5")]
)
def test_j4_promo_value_ranges(edition, finance, kind, value):
    response = finance.post(
        f"{base(edition)}/promo-codes", {"code": "X", "kind": kind, "value": value}
    )
    assert response.status_code == 400
    assert "value" in response.json()["fields"]


def test_j4_used_code_keeps_its_uses(edition, finance):
    code = PromoCode.objects.create(
        edition=edition, code="ETU", kind="percent", value=Decimal("10"), consumed_uses=3
    )
    url = f"{base(edition)}/promo-codes/{code.pk}"
    assert finance.patch(url, {"max_uses": 2}, format="json").status_code == 400
    assert finance.patch(url, {"max_uses": 3}, format="json").status_code == 200
    assert finance.delete(url).status_code == 409
    assert finance.patch(url, {"is_active": False}, format="json").json()["is_active"] is False


def test_secretariat_reads_catalog_without_writing(edition):
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    assert client.get(f"{base(edition)}/promo-codes").status_code == 200
    response = client.post(f"{base(edition)}/promo-codes", {"code": "X", "kind": "percent"})
    assert response.status_code == 403
