"""Paramètres des inscriptions (plan L6, J2, J5, J9) : devise, pays locaux, moyens,
échéances, annulation."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.accounts.roles import Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog
from apps.registrations.models import Fee, Zone
from apps.registrations.services.settings import registration_settings, zone_for
from apps.registrations.tests.factories import make_category, make_registration

pytestmark = pytest.mark.django_db


def url(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/registrations/settings"


@pytest.fixture
def edition():
    return EditionFactory(country="CI")


@pytest.fixture
def finance(edition):
    return client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))


def test_defaults_xof_transfer_and_onsite_72_hours_30_days(edition):
    """J2 : XOF par défaut ; J5 : 72 h en ligne, 30 jours par virement ; J9 : remboursement
    intégral avant la date limite, aucun après ; paiement en ligne désactivé tant qu'aucun
    fournisseur n'est configuré."""
    response = client_for(make_member(edition, Role.CHAIR)).get(url(edition))
    assert response.status_code == 200
    assert response.json() == {
        "currency": "XOF",
        "local_countries": [],
        "online_enabled": False,
        "transfer_enabled": True,
        "onsite_enabled": True,
        "online_deadline_hours": 72,
        "transfer_deadline_days": 30,
        "cancellation_deadline": None,
        "cancellation_deadline_local": None,
        "refund_percent_before": 100,
        "refund_percent_after": 0,
    }


def test_written_by_finance_committee_and_audited(edition, finance):
    response = finance.patch(
        url(edition),
        {"local_countries": ["sn", "CI", "ci"], "refund_percent_before": 80},
        format="json",
    )
    assert response.status_code == 200, response.content
    assert response.json()["local_countries"] == ["CI", "SN"]
    log = AuditLog.objects.get(action="registrations.settings_changed")
    assert log.before == {"local_countries": [], "refund_percent_before": 100}
    assert log.after == {"local_countries": ["CI", "SN"], "refund_percent_before": 80}


def test_secretariat_reads_but_cannot_write_pricing_settings(edition):
    """J1 : le secrétariat gère les inscriptions, pas les tarifs ni leurs paramètres."""
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    assert client.get(url(edition)).status_code == 200
    response = client.patch(url(edition), {"currency": "EUR"}, format="json")
    assert response.status_code == 403


def test_unknown_country_is_refused(edition, finance):
    response = finance.patch(url(edition), {"local_countries": ["ZZ"]}, format="json")
    assert response.status_code == 400
    assert "local_countries" in response.json()["fields"]


@pytest.mark.parametrize("value", [-1, 101])
def test_refund_percentages_range_0_to_100(edition, finance, value):
    response = finance.patch(url(edition), {"refund_percent_after": value}, format="json")
    assert response.status_code == 400
    assert "refund_percent_after" in response.json()["fields"]


def test_j2_currency_frozen_once_a_registration_exists(edition, finance):
    """J2 : une devise par édition, figée dès la première inscription (409)."""
    make_registration(edition, VerifiedUserFactory())
    response = finance.patch(url(edition), {"currency": "EUR"}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "setting_frozen"
    assert registration_settings(edition).currency == "XOF"


def test_j2_currency_change_requires_amounts_exact_in_new_currency(edition, finance):
    """EUR → XOF : un tarif de 12,50 n'a pas de sens en francs CFA (aucune décimale)."""
    finance.patch(url(edition), {"currency": "EUR"}, format="json")
    category = make_category(edition)
    Fee.objects.create(category=category, period="early", zone="local", amount=Decimal("12.50"))
    response = finance.patch(url(edition), {"currency": "XOF"}, format="json")
    assert response.status_code == 400
    assert "currency" in response.json()["fields"]
    Fee.objects.update(amount=Decimal("12"))
    assert finance.patch(url(edition), {"currency": "XOF"}, format="json").status_code == 200


def test_j2_zone_local_from_settings_or_edition_country(edition):
    settings = registration_settings(edition)
    assert zone_for(edition, settings, "CI") == Zone.LOCAL
    assert zone_for(edition, settings, "FR") == Zone.INTERNATIONAL
    assert zone_for(edition, settings, "") == Zone.INTERNATIONAL
    settings.local_countries = ["SN", "BF"]
    assert zone_for(edition, settings, "CI") == Zone.INTERNATIONAL
    assert zone_for(edition, settings, "BF") == Zone.LOCAL


def test_unchanged_values_write_no_audit_entry(edition, finance):
    assert finance.patch(url(edition), {"currency": "XOF"}, format="json").status_code == 200
    assert not AuditLog.objects.filter(action="registrations.settings_changed").exists()


def test_d13_cancellation_deadline_entered_in_edition_local_time():
    """D13 : la date limite d'annulation se saisit à l'heure de l'édition ; le serveur la
    stocke en UTC et la renvoie dans les deux formes."""
    edition = EditionFactory(country="FR", timezone="Europe/Paris")
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))
    response = client.patch(
        url(edition), {"cancellation_deadline_local": "2027-05-01T00:00"}, format="json"
    )
    assert response.status_code == 200, response.content
    assert response.json()["cancellation_deadline"] == "2027-04-30T22:00:00Z"
    assert response.json()["cancellation_deadline_local"] == "2027-05-01T00:00:00"
    stored = registration_settings(edition).cancellation_deadline
    assert stored.isoformat() == "2027-04-30T22:00:00+00:00"
    # Valeur UTC en lecture seule : ignorée en écriture.
    client.patch(url(edition), {"cancellation_deadline": "2030-01-01T00:00:00Z"}, format="json")
    assert registration_settings(edition).cancellation_deadline == stored
    # Effacement.
    response = client.patch(url(edition), {"cancellation_deadline_local": None}, format="json")
    assert response.json()["cancellation_deadline_local"] is None


def test_d13_nonexistent_local_time_refused_on_the_entered_field():
    """D13 : heure inexistante (passage à l'heure d'été) refusée, erreur sur le champ saisi."""
    edition = EditionFactory(country="FR", timezone="Europe/Paris")
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))
    response = client.patch(
        url(edition), {"cancellation_deadline_local": "2027-03-28T02:30"}, format="json"
    )
    assert response.status_code == 400
    assert list(response.json()["fields"]) == ["cancellation_deadline_local"]
