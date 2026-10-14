"""Édition de démonstration (plan L9, S10)."""

from __future__ import annotations

import io

import pytest
from allauth.mfa.models import Authenticator
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User, UserRole
from apps.accounts.roles import MFA_REQUIRED_ROLES, Role
from apps.accounts.tests.roles_helpers import client_for
from apps.conferences.services import current_public_edition
from apps.core.models import AuditLog
from apps.qa.demo import ACCOUNTS
from apps.qa.fictitious import FICTITIOUS_DOMAIN

pytestmark = pytest.mark.django_db


def demo() -> str:
    output = io.StringIO()
    call_command("seed_demo", "--confirm-fictitious", stdout=output)
    return output.getvalue()


def test_s10_demo_edition_has_one_account_per_role():
    output = demo()
    edition = current_public_edition()
    assert edition is not None and edition.code == "DEMO"
    assert User.objects.count() == len(ACCOUNTS)
    assert not User.objects.exclude(email__endswith="@" + FICTITIOUS_DOMAIN).exists()
    roles = set(UserRole.objects.filter(edition=edition).values_list("role", flat=True))
    assert {Role.ADMIN, Role.CHAIR, Role.SC_CHAIR, Role.SC_MEMBER, Role.OC_MEMBER} <= roles
    assert {Role.VOLUNTEER, Role.SIGNATORY, Role.SPEAKER} <= roles
    functions = set(
        UserRole.objects.filter(edition=edition, role=Role.OC_MEMBER).values_list(
            "oc_function", flat=True
        )
    )
    assert functions == {
        "program",
        "finance",
        "secretariat",
        "logistics",
        "communication",
        "external_relations",
        "volunteers",
    }
    # 2FA activée pour chaque rôle de gestion (recommandée, T1), et pour eux seulement.
    managed = set(
        UserRole.objects.filter(edition=edition, role__in=MFA_REQUIRED_ROLES).values_list(
            "user_id", flat=True
        )
    )
    with_totp = set(Authenticator.objects.values_list("user_id", flat=True))
    assert with_totp == managed
    assert "mot de passe des comptes" in output and "secret TOTP" in output
    assert AuditLog.objects.filter(action="qa.demo_seeded").exists()


def test_s10_demo_accounts_reach_their_screens():
    demo()
    edition = current_public_edition()
    finance = client_for(User.objects.get(email=f"co.finances@{FICTITIOUS_DOMAIN}"))
    url = f"/v1/manage/editions/{edition.pk}/registrations/categories"
    assert finance.get(url).status_code == 200
    reviewer = client_for(User.objects.get(email=f"relecteur1@{FICTITIOUS_DOMAIN}"))
    assert reviewer.get(f"/v1/manage/editions/{edition.pk}/reviews/assignments").json() == []


def test_s10_demo_guards_and_coexistence_with_volume():
    with pytest.raises(CommandError, match="confirm-fictitious"):
        call_command("seed_demo")
    demo()
    with pytest.raises(CommandError, match="existe déjà"):
        demo()
    # Même conférence fictive : les données de volume s'ajoutent sans conflit.
    call_command(
        "seed_volume",
        "--confirm-fictitious",
        *["--submissions", "2", "--reviewers", "2", "--participants", "2", "--drafts", "1"],
        stdout=io.StringIO(),
    )
    assert User.objects.filter(email=f"comite0001@{FICTITIOUS_DOMAIN}").exists()


def test_s10_demo_refused_on_real_data():
    from apps.accounts.tests.factories import VerifiedUserFactory

    VerifiedUserFactory(email="personne@exemple.org")
    with pytest.raises(CommandError, match="données réelles"):
        demo()
