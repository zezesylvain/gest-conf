"""Contrôles d'intégrité des inscriptions et commande ``expire_registrations`` (plan L6)."""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.core.actor import Actor
from apps.registrations import integrity
from apps.registrations.models import Registration, RegistrationOption
from apps.registrations.services import orders
from apps.registrations.tests.helpers import grid, open_edition, option, participant_user

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = open_edition()
    grid(edition, "etudiant", early_local="25000")
    option(edition, "diner", quota=5)
    return edition


def test_integrity_clean_after_orders_then_detects_drift(edition):
    for _ in range(2):
        orders.place_order(
            edition,
            participant_user(),
            category="etudiant",
            options=["diner"],
            method="transfer",
            actor=COMMAND,
        )
    assert integrity.check_totals() == []
    assert integrity.check_reservations() == []
    RegistrationOption.objects.filter(code="diner").update(reserved=1)
    assert integrity.check_reservations()
    Registration.objects.filter(pk=Registration.objects.first().pk).update(total=1)
    assert integrity.check_totals()


def test_j5_expire_registrations_command_is_idempotent(edition):
    registration = orders.place_order(
        edition, participant_user(), category="etudiant", method="transfer", actor=COMMAND
    )
    Registration.objects.filter(pk=registration.pk).update(
        due_at=timezone.now() - dt.timedelta(minutes=1)
    )
    call_command("expire_registrations", verbosity=0)
    call_command("expire_registrations", verbosity=0)
    registration.refresh_from_db()
    assert registration.status == "expired"
