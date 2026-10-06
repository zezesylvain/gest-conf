"""Page publique « Inscription » et devis du participant (plan L6, J2 à J4, J13)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Profile
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for
from apps.conferences.models import Conference
from apps.registrations.models import RegistrationOption
from apps.registrations.services.settings import registration_settings
from apps.registrations.tests.helpers import grid, open_edition, option, set_window

pytestmark = pytest.mark.django_db

PUBLIC = "/v1/public/registration"
QUOTE = "/v1/registrations/quote"


@pytest.fixture
def edition():
    edition = open_edition()
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    grid(edition, "etudiant", early_local="25000", early_international="50000")
    hidden = grid(edition, "ancienne", early_local="1")
    hidden.is_active = False
    hidden.save()
    workshop = option(edition, "atelier", quota=30, reserved=29)
    workshop.categories.set(edition.registration_categories.filter(code="etudiant"))
    option(edition, "visite", is_active=False)
    return edition


def participant(country: str = "CI"):
    user = VerifiedUserFactory()
    Profile.objects.create(user=user, first_name="Awa", last_name="Zadi", country=country)
    return client_for(user)


def test_j13_public_registration_lists_active_catalog_without_remaining_places(edition):
    response = APIClient().get(PUBLIC)
    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=300"
    body = response.json()
    assert body["currency"] == "XOF"
    assert body["methods"] == ["transfer", "onsite"]
    assert body["local_countries"] == ["CI"]
    assert [category["code"] for category in body["categories"]] == ["etudiant"]
    assert body["categories"][0]["fees"] == [
        {"period": "early", "zone": "international", "amount": "50000.00"},
        {"period": "early", "zone": "local", "amount": "25000.00"},
    ]
    assert body["options"] == [
        {
            "code": "atelier",
            "label_fr": "Atelier",
            "label_en": "",
            "description_fr": "",
            "description_en": "",
            "price_local": "10000.00",
            "price_international": "20000.00",
            "limited": True,
            "categories": ["etudiant"],
        }
    ]
    assert body["opens_at"] and body["early_bird_end"] and body["closes_at"]
    assert "reserved" not in str(body) and "quota" not in str(body)


def test_public_registration_404_without_published_current_edition():
    assert APIClient().get(PUBLIC).status_code == 404


def test_j2_quote_uses_profile_country_and_reserves_nothing(edition):
    client = participant("FR")
    response = client.post(QUOTE, {"category": "etudiant", "options": ["atelier"]}, format="json")
    assert response.status_code == 200, response.content
    body = response.json()
    assert (body["period"], body["zone"], body["currency"]) == ("early", "international", "XOF")
    assert [line["amount"] for line in body["lines"]] == ["50000.00", "20000.00"]
    assert body["total"] == "70000.00"
    assert RegistrationOption.objects.get(code="atelier").reserved == 29


def test_quote_requires_country_in_profile(edition):
    response = participant("").post(QUOTE, {"category": "etudiant"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "profile_incomplete"
    assert "country" in response.json()["fields"]


def test_quote_refused_when_registration_closed(edition):
    window = registration_settings(edition)  # paramètres créés
    assert window.currency == "XOF"
    set_window(edition)  # aucune date d'ouverture
    response = participant().post(QUOTE, {"category": "etudiant"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "registration_closed"


def test_quote_requires_authentication(edition):
    assert APIClient().post(QUOTE, {"category": "etudiant"}, format="json").status_code == 401


def test_quote_total_is_decimal_string(edition):
    body = participant().post(QUOTE, {"category": "etudiant"}, format="json").json()
    assert Decimal(body["total"]) == Decimal("25000")
