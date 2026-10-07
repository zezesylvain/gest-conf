"""Partenaires (plan L8, N5) : service, page publique, logo, journal, budget, API."""

from __future__ import annotations

import datetime as dt
import io
from decimal import Decimal

import pytest
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import Conference, EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog, PublicFile, PublicFileKind
from apps.logistics.models import BudgetSource
from apps.logistics.services import budget
from apps.portal.services import pending_changes
from apps.sponsors import services
from apps.sponsors.models import SponsorStatus

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


def png(size=(300, 120)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "orange").save(output, "PNG")
    return output.getvalue()


@pytest.fixture
def edition(settings, tmp_path):
    settings.GESTCONF_FILES_DIR = str(tmp_path)
    edition = EditionFactory(status=EditionStatus.PUBLISHED)
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    return edition


def test_n5_level_validation_and_deletion_only_when_unused(edition):
    with pytest.raises(Invalid) as error:
        services.create_level(edition, {"name_fr": " ", "amount": "1.5"}, actor=COMMAND)
    assert set(error.value.fields) == {"name_fr", "amount"}
    level = services.create_level(
        edition,
        {"name_fr": "Or", "amount": "5000000", "benefits_fr": "- Stand\n- Logo sur les badges"},
        actor=COMMAND,
    )
    sponsor = services.create_sponsor(edition, {"name": "Orange", "level": level.pk}, actor=COMMAND)
    # Les contreparties du niveau sont recopiées sur la fiche.
    assert list(sponsor.benefits.values_list("label", flat=True)) == [
        "Stand",
        "Logo sur les badges",
    ]
    with pytest.raises(RuleViolation):
        services.delete_level(level, actor=COMMAND)
    services.update_sponsor(sponsor, {"level": None}, actor=COMMAND)
    services.delete_level(level, actor=COMMAND)
    other = EditionFactory()
    foreign = services.create_level(other, {"name_fr": "Or"}, actor=COMMAND)
    with pytest.raises(Invalid) as error:
        services.update_sponsor(sponsor, {"level": foreign.pk}, actor=COMMAND)
    assert "level" in error.value.fields


def test_n5_contact_is_never_written_to_the_audit_log(edition):
    sponsor = services.create_sponsor(
        edition,
        {
            "name": "Orange",
            "contact_name": "Awa Traoré",
            "contact_email": "awa.traore@orange.ci",
            "contact_phone": "+225 07 00 00 00",
            "description_fr": "Écrire à presse@orange.ci",
        },
        actor=COMMAND,
    )
    services.update_sponsor(sponsor, {"contact_email": "autre@orange.ci"}, actor=COMMAND)
    entries = list(AuditLog.objects.filter(action__startswith="sponsor.").order_by("id"))
    text = str([(entry.before, entry.after) for entry in entries])
    assert "orange.ci" not in text.replace("p***@orange.ci", "")
    assert "Awa" not in text and "+225" not in text
    assert entries[-1].after == {"contact_changed": True, "public": False}


def test_n5_contribution_received_requires_amount_and_date_and_feeds_the_budget(edition):
    sponsor = services.create_sponsor(edition, {"name": "Orange"}, actor=COMMAND)
    with pytest.raises(Invalid):
        services.update_sponsor(sponsor, {"status": "received"}, actor=COMMAND)
    with pytest.raises(Invalid):  # XOF : pas de décimale
        services.update_sponsor(sponsor, {"agreed_amount": "10.5"}, actor=COMMAND)
    services.update_sponsor(
        sponsor,
        {
            "status": SponsorStatus.RECEIVED,
            "agreed_amount": "3000000",
            "received_amount": "2000000",
            "received_on": dt.date(2027, 3, 1),
        },
        actor=COMMAND,
    )
    declined = services.create_sponsor(
        edition, {"name": "Refus", "status": "declined", "received_amount": "99"}, actor=COMMAND
    )
    assert declined.status == SponsorStatus.DECLINED
    assert services.received_total(edition) == Decimal("2000000")
    totals = services.totals(edition)
    assert (totals["agreed"], totals["received"]) == (Decimal("3000000"), Decimal("2000000"))
    # N4 : la ligne « partenariats » du budget lit le total reçu.
    lines = dict(
        (line.source, actual)
        for line, actual in budget.lines(edition)
        if line.source != BudgetSource.MANUAL
    )
    assert lines[BudgetSource.SPONSORS] == Decimal("2000000")


def test_n5_public_page_lists_published_sponsors_by_level_without_private_data(edition):
    gold = services.create_level(edition, {"name_fr": "Or", "logo_size": "large"}, actor=COMMAND)
    silver = services.create_level(edition, {"name_fr": "Argent", "position": 1}, actor=COMMAND)
    shown = services.create_sponsor(
        edition,
        {
            "name": "Orange",
            "level": gold.pk,
            "published": True,
            "website": "https://orange.ci",
            "contact_email": "awa@orange.ci",
            "agreed_amount": "3000000",
            "note": "Interne",
        },
        actor=COMMAND,
    )
    services.create_sponsor(edition, {"name": "Caché", "level": silver.pk}, actor=COMMAND)
    services.create_sponsor(edition, {"name": "Média", "published": True}, actor=COMMAND)
    services.set_logo(shown, data=png(), name="orange.png", actor=COMMAND)
    response = APIClient().get("/v1/public/sponsors")
    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=300"
    body = response.json()
    assert [level["name_fr"] for level in body["levels"]] == ["Or"]
    card = body["levels"][0]["sponsors"][0]
    assert set(card) == {
        "name",
        "website",
        "description_fr",
        "description_en",
        "logo_url",
        "logo_width",
        "logo_height",
    }
    assert card["name"] == "Orange" and card["logo_url"].startswith("/v1/public/files/")
    assert [other["name"] for other in body["others"]] == ["Média"]
    assert "awa@orange.ci" not in response.content.decode()
    assert "3000000" not in response.content.decode()
    # Le logo est servi, réduit à 600 px au plus, et absent de l'écran des fichiers du CMS.
    assert APIClient().get(card["logo_url"]).status_code == 200
    logo = PublicFile.objects.get(kind=PublicFileKind.LOGO)
    assert logo.width <= 600 and logo.published


def test_n5_logo_follows_publication_and_is_replaced(edition):
    sponsor = services.create_sponsor(edition, {"name": "Orange"}, actor=COMMAND)
    sponsor = services.set_logo(sponsor, data=png(), name="a.png", actor=COMMAND)
    first = sponsor.logo
    assert first.published is False
    from apps.portal.services import public_file_url

    assert APIClient().get(public_file_url(first)).status_code == 404
    sponsor = services.update_sponsor(sponsor, {"published": True}, actor=COMMAND)
    first.refresh_from_db()
    assert first.published is True
    sponsor = services.set_logo(sponsor, data=png((100, 40)), name="b.png", actor=COMMAND)
    assert not PublicFile.objects.filter(pk=first.pk).exists()
    services.delete_sponsor(sponsor, actor=COMMAND)
    assert not PublicFile.objects.filter(kind=PublicFileKind.LOGO).exists()
    # Le CMS ne liste pas les logos.
    admin = make_member(edition, Role.ADMIN)
    services.set_logo(
        services.create_sponsor(edition, {"name": "B"}, actor=COMMAND),
        data=png(),
        name="c.png",
        actor=COMMAND,
    )
    files = client_for(admin).get(f"/v1/manage/editions/{edition.pk}/portal/files").json()
    assert files == []


def test_n5_only_public_changes_count_as_unpublished_portal_changes(edition):
    """L2 : la gestion compte les modifications non publiées ; un changement privé (montant,
    contact, note) ou celui d'un partenaire non publié n'en est pas une."""
    level = services.create_level(edition, {"name_fr": "Or"}, actor=COMMAND)
    assert pending_changes(edition).count() == 1  # un niveau est public
    hidden = services.create_sponsor(edition, {"name": "Caché"}, actor=COMMAND)
    services.update_sponsor(hidden, {"website": "https://cache.ci"}, actor=COMMAND)
    assert pending_changes(edition).count() == 1
    shown = services.create_sponsor(
        edition, {"name": "Orange", "level": level.pk, "published": True}, actor=COMMAND
    )
    assert pending_changes(edition).count() == 2
    services.update_sponsor(shown, {"note": "Relancer", "agreed_amount": "100"}, actor=COMMAND)
    assert pending_changes(edition).count() == 2
    services.update_sponsor(shown, {"description_fr": "Opérateur"}, actor=COMMAND)
    services.update_sponsor(hidden, {"published": True}, actor=COMMAND)
    assert pending_changes(edition).count() == 4


def test_n5_api_rights_benefits_and_export(edition):
    relations = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.EXTERNAL_RELATIONS)
    finance = make_member(edition, Role.OC_MEMBER, oc_function=OcFunction.FINANCE)
    base = f"/v1/manage/editions/{edition.pk}/sponsors"
    client = client_for(relations)
    response = client.post(base, {"name": "Orange", "contact_email": "a@orange.ci"}, format="json")
    assert response.status_code == 201
    sponsor_id = response.json()["id"]
    response = client.post(f"{base}/{sponsor_id}/benefits", {"label": "Stand"}, format="json")
    benefit = response.json()["benefits"][0]
    response = client.patch(
        f"{base}/{sponsor_id}/benefits/{benefit['id']}",
        {"delivered_on": "2027-06-01"},
        format="json",
    )
    assert response.json()["benefits"][0]["delivered_on"] == "2027-06-01"
    listed = client_for(finance).get(base).json()
    assert listed["sponsors"][0]["benefits_delivered"] == 1
    # Les finances lisent, sans écrire.
    response = client_for(finance).patch(f"{base}/{sponsor_id}", {"name": "X"}, format="json")
    assert response.status_code == 403
    response = client.get(f"{base}/export?file_format=csv")
    assert response.status_code == 200 and "a@orange.ci" in response.content.decode()
    assert AuditLog.objects.filter(action="sponsor.exported").count() == 1
    response = client_for(relations, recent_auth=False).get(f"{base}/export")
    assert response.status_code == 403
