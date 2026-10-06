"""RG-11 (plan L6, J10) : si l'édition l'exige, une communication placée dont aucun
présentateur n'a d'inscription confirmée produit un conflit « registration », signalé dans
le brouillon et bloquant à la publication."""

from __future__ import annotations

import pytest

from apps.core.errors import RuleViolation
from apps.program.serializers import board_data
from apps.program.services import planning, publication
from apps.program.tests.helpers import COMMAND, coauthor, confirmed, edition, local, session
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_registration

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    current = edition(presenter_registration_required=True)
    morning = session(current, local(1, 9), local(1, 12))
    paper = confirmed(current, duration=20)
    planning.place_submission(morning, paper, actor=COMMAND)
    return current, morning, paper


def kinds(current):
    return [conflict.kind for conflict in planning.detect_conflicts(current)]


def test_rg11_unregistered_presenter_is_a_conflict(world):
    current, morning, _paper = world
    conflict = next(c for c in planning.detect_conflicts(current) if c.kind == "registration")
    assert conflict.sessions == (morning.pk,)
    assert conflict.person == "Awa Zadi"
    board = board_data(current)
    assert board["sessions"][0]["slots"][0]["submission"]["presenter_registered"] is False


def test_rg11_confirmed_registration_of_the_presenter_resolves_it(world):
    current, _morning, paper = world
    make_registration(current, paper.submitter, status=RegistrationStatus.PENDING)
    assert "registration" in kinds(current)  # en attente : pas encore inscrit
    paper.submitter.registrations.update(status=RegistrationStatus.CONFIRMED, qr_token="q" * 32)
    assert "registration" not in kinds(current)


def test_rg11_presenter_without_account_recognized_by_registered_address(world):
    from apps.accounts.tests.factories import VerifiedUserFactory

    current, _morning, paper = world
    paper.authors.update(is_presenter=False)
    coauthor(paper, email="Mariam.Traore@univ.test")
    other = VerifiedUserFactory(email="mariam.traore@univ.test")
    make_registration(current, other, status=RegistrationStatus.CONFIRMED)
    assert "registration" not in kinds(current)


def test_rg11_disabled_by_default(world):
    current, _morning, _paper = world
    current.presenter_registration_required = False
    current.save()
    assert "registration" not in kinds(current)


def test_rg11_blocks_publication(world):
    current, _morning, _paper = world
    with pytest.raises(RuleViolation) as error:
        publication.publish_program(current, actor=COMMAND)
    assert error.value.code == "program_conflicts"
