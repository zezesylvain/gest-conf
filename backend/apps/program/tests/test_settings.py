"""Paramètres du programme de l'édition (plan L5, I17) : tampon RG-13 et RG-11."""

from __future__ import annotations

import pytest

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def url(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}/program/settings"


@pytest.fixture
def edition():
    return EditionFactory()


def test_defaults_rg13_buffer_zero_and_rg11_disabled(edition):
    """RG-11 désactivée par défaut (sans effet avant L6) ; RG-13 sans tampon par défaut."""
    response = client_for(make_member(edition, Role.CHAIR)).get(url(edition))
    assert response.status_code == 200
    assert response.json() == {
        "session_buffer_minutes": 0,
        "presenter_registration_required": False,
    }


def test_rg13_buffer_written_by_program_committee_and_audited(edition):
    member = make_member(edition, Role.OC_MEMBER, oc_function="program")
    response = client_for(member).patch(
        url(edition), {"session_buffer_minutes": 10, "presenter_registration_required": True}
    )
    assert response.status_code == 200
    assert response.json()["session_buffer_minutes"] == 10
    log = AuditLog.objects.get(action="program.settings_changed")
    assert log.before == {"session_buffer_minutes": 0, "presenter_registration_required": False}
    assert log.after == {"session_buffer_minutes": 10, "presenter_registration_required": True}


@pytest.mark.parametrize("value", [-1, 31])
def test_rg13_buffer_range_0_to_30(edition, value):
    admin = make_member(edition, Role.ADMIN)
    response = client_for(admin).patch(url(edition), {"session_buffer_minutes": value})
    assert response.status_code == 400
    assert "session_buffer_minutes" in response.json()["fields"]


def test_unchanged_values_write_no_audit_entry(edition):
    admin = make_member(edition, Role.ADMIN)
    response = client_for(admin).patch(url(edition), {"session_buffer_minutes": 0})
    assert response.status_code == 200
    assert not AuditLog.objects.filter(action="program.settings_changed").exists()


def test_other_committee_functions_only_read(edition):
    """I1 et Q12 : les autres fonctions du CO lisent le programme sans l'écrire."""
    finance = client_for(make_member(edition, Role.OC_MEMBER, oc_function="finance"))
    assert finance.get(url(edition)).status_code == 200
    assert finance.patch(url(edition), {"session_buffer_minutes": 5}).status_code == 403


def test_archived_edition_is_read_only(edition):
    admin = make_member(edition, Role.ADMIN)
    edition.status = EditionStatus.ARCHIVED
    edition.save(update_fields=["status"])
    response = client_for(admin).patch(url(edition), {"session_buffer_minutes": 5})
    assert response.status_code == 409


def test_rg13_buffer_change_reflows_slots_and_bumps_revision():
    """RG-13 : un nouveau tampon recalcule les créneaux existants et change la révision (I14) ;
    sinon les heures seraient fausses et le contrôle d'intégrité les signalerait."""
    from apps.program.integrity import check_slots
    from apps.program.models import Slot
    from apps.program.services import planning
    from apps.program.tests.helpers import COMMAND, confirmed, local, session, utc
    from apps.program.tests.helpers import edition as program_edition

    current = program_edition()
    item = session(current, local(1, 9), local(1, 10, 30))
    for _index in range(2):
        planning.place_submission(item, confirmed(current, duration=20), actor=COMMAND)
    revision = planning.program_state(current).revision

    response = client_for(make_member(current, Role.ADMIN)).patch(
        url(current), {"session_buffer_minutes": 5}
    )

    assert response.status_code == 200
    assert Slot.objects.get(session=item, position=1).starts_at == utc(1, 9, 25)
    assert planning.program_state(current).revision == revision + 1
    assert check_slots() == []
