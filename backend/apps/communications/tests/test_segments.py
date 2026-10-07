"""Registre des segments des envois groupés (plan L8, N1, N11)."""

from __future__ import annotations

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.communications import segments
from apps.communications.segments import Segment
from apps.core.errors import Invalid, NotAllowed

pytestmark = pytest.mark.django_db


@pytest.fixture
def registry(monkeypatch):
    """Registre vide pour le test, restauré ensuite."""
    monkeypatch.setattr(segments, "_SEGMENTS", {})
    return segments


def everyone(_edition):
    return User.objects.all()


def test_n1_segments_are_declared_once_and_listed_in_order(registry):
    late = Segment("reviews.late", "Relecteurs en retard", everyone, 20, "reviews.manage")
    confirmed = Segment("registrations.confirmed", "Inscrits confirmés", everyone, 10)
    registry.register_segment(late)
    registry.register_segment(confirmed)
    registry.register_segment(confirmed)  # déclaration répétée : ignorée
    assert [item.code for item in registry.all_segments()] == [
        "registrations.confirmed",
        "reviews.late",
    ]
    with pytest.raises(ValueError):
        registry.register_segment(Segment("reviews.late", "Autre", everyone))


def test_n11_segment_requiring_a_capability_is_reserved_to_its_holders(registry):
    """« Relecteurs en retard » lit l'état des évaluations : ``reviews.manage`` exigée (le CO
    n'a aucun accès aux évaluations)."""
    registry.register_segment(Segment("reviews.late", "Retard", everyone, 20, "reviews.manage"))
    registry.register_segment(Segment("registrations.confirmed", "Confirmés", everyone, 10))
    communication = {"communications.send"}
    assert [item.code for item in registry.available_segments(communication)] == [
        "registrations.confirmed"
    ]
    with pytest.raises(NotAllowed):
        registry.get_segment("reviews.late", communication)
    assert registry.get_segment("reviews.late", {"reviews.manage"}).code == "reviews.late"
    with pytest.raises(Invalid):
        registry.get_segment("inconnu", communication)


def test_n11_recipients_are_active_accounts_only(registry):
    active = VerifiedUserFactory()
    VerifiedUserFactory(is_active=False)
    VerifiedUserFactory(anonymized_at=timezone.now())
    segment = Segment("all", "Tous", everyone)
    assert list(registry.recipients(None, segment)) == [active]
