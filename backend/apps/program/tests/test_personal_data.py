"""Données personnelles du programme (RG-18 ; plan L5 §3) : export, refus d'anonymiser tant
que la personne figure au programme d'une édition non archivée, noms retirés des
instantanés publiés."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.models import Profile
from apps.accounts.services.personal_data import (
    active_duties,
    anonymize_user,
    export_user_data,
)
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import RuleViolation
from apps.program.models import (
    ProgramPublication,
    Room,
    Session,
    SessionKind,
    SessionRole,
    SessionRoleKind,
)

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def chaired():
    """Une personne présidente de séance, sans rôle d'édition, dans un programme publié."""
    edition = EditionFactory()
    person = VerifiedUserFactory()
    Profile.objects.update_or_create(
        user=person, defaults={"first_name": "Mariam", "last_name": "Traoré"}
    )
    start = dt.datetime(2027, 3, 1, 9, tzinfo=dt.UTC)
    session = Session.objects.create(
        edition=edition,
        kind=SessionKind.PARALLEL,
        title_fr="Santé publique",
        room=Room.objects.create(edition=edition, name="Amphi A"),
        starts_at=start,
        ends_at=start + dt.timedelta(hours=1, minutes=30),
    )
    SessionRole.objects.create(session=session, user=person, role=SessionRoleKind.CHAIR)
    ProgramPublication.objects.create(
        edition=edition,
        version=1,
        revision=1,
        published_at=timezone.now(),
        snapshot={"sessions": [{"title_fr": "Santé publique", "chairs": ["Mariam Traoré"]}]},
    )
    return edition, person


def test_rg18_export_contains_session_roles(chaired):
    _edition, person = chaired
    data = export_user_data(person, actor=COMMAND)
    assert data["session_roles"][0]["role"] == "chair"
    assert data["session_roles"][0]["session"] == "Santé publique"


def test_rg18_anonymization_refused_while_in_programme_of_open_edition(chaired):
    edition, person = chaired
    assert f"program:{edition.code}" in active_duties(person)
    with pytest.raises(RuleViolation) as error:
        anonymize_user(person, actor=COMMAND, reason="Demande écrite")
    assert error.value.code == "account_has_active_duties"


def test_rg18_anonymization_scrubs_published_snapshots(chaired):
    edition, person = chaired
    edition.status = EditionStatus.ARCHIVED
    edition.save(update_fields=["status"])
    anonymize_user(person, actor=COMMAND, reason="Demande écrite")
    snapshot = ProgramPublication.objects.get(edition=edition).snapshot
    assert "Traoré" not in str(snapshot)
    assert snapshot["sessions"][0]["title_fr"] == "Santé publique"
