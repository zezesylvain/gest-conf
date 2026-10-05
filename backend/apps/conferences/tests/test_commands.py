"""Commandes d'exploitation de l'édition et des rôles (D1 : autorité de plateforme)."""

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import RoleInvitation, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.conferences.models import Conference, Edition, EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def create_edition(*extra: str) -> Edition:
    call_command("create_conference", "--slug", "gestconf", "--name-fr", "Conférence")
    call_command(
        "create_edition",
        "--conference",
        "gestconf",
        "--code",
        "GC27",
        "--slug",
        "gc-2027",
        "--year",
        "2027",
        "--title-fr",
        "GEST-CONF 2027",
        *extra,
    )
    return Edition.objects.get(code="GC27")


def test_create_edition_with_existing_admin_account():
    user = VerifiedUserFactory(email="admin@example.org")
    edition = create_edition("--admin-email", "Admin@Example.org", "--current")
    assert UserRole.objects.filter(
        user=user, edition=edition, role=Role.ADMIN, status=UserRoleStatus.ACTIVE
    ).exists()
    assert Conference.objects.get(slug="gestconf").current_edition == edition
    assert AuditLog.objects.filter(action="edition.created", actor_kind="command").exists()


def test_create_edition_invites_unknown_admin():
    edition = create_edition("--admin-email", "nouveau@example.org")
    invitation = RoleInvitation.objects.get(edition=edition)
    assert invitation.role == Role.ADMIN
    assert invitation.invited_by is None
    assert not UserRole.objects.filter(edition=edition).exists()


def test_create_edition_unknown_conference():
    with pytest.raises(CommandError):
        call_command(
            "create_edition",
            "--conference",
            "absente",
            "--code",
            "GC27",
            "--slug",
            "x",
            "--year",
            "2027",
            "--title-fr",
            "X",
        )


def test_create_edition_invalid_code_rolls_back():
    call_command("create_conference", "--slug", "gestconf", "--name-fr", "Conférence")
    with pytest.raises(CommandError):
        call_command(
            "create_edition",
            "--conference",
            "gestconf",
            "--code",
            "gc-27",
            "--slug",
            "x",
            "--year",
            "2027",
            "--title-fr",
            "X",
        )
    assert not Edition.objects.exists()


def test_grant_and_revoke_role_commands():
    edition = EditionFactory()
    user = VerifiedUserFactory()
    args = ["--email", user.email, "--edition", edition.code, "--role", Role.SC_MEMBER]
    call_command("grant_role", *args, "--reason", "Nomination")
    user_role = UserRole.objects.get(user=user, edition=edition)
    assert user_role.status == UserRoleStatus.ACTIVE
    call_command("revoke_role", *args, "--reason", "Fin de mandat")
    user_role.refresh_from_db()
    assert user_role.status == UserRoleStatus.REVOKED
    assert AuditLog.objects.get(action="role.revoked").reason == "Fin de mandat"


def test_grant_role_unknown_account():
    edition = EditionFactory()
    with pytest.raises(CommandError):
        call_command(
            "grant_role",
            "--email",
            "absent@example.org",
            "--edition",
            edition.code,
            "--role",
            Role.CHAIR,
            "--reason",
            "x",
        )


def test_set_edition_status_command_can_roll_back():
    edition = EditionFactory(status=EditionStatus.PUBLISHED)
    call_command("set_edition_status", edition.code, "draft", "--reason", "Erreur")
    edition.refresh_from_db()
    assert edition.status == EditionStatus.DRAFT
    assert AuditLog.objects.get(action="edition.status_changed").reason == "Erreur"


def test_set_edition_status_refuses_incomplete_publication():
    edition = EditionFactory()
    with pytest.raises(CommandError):
        call_command("set_edition_status", edition.code, "published", "--reason", "Ouverture")


def test_set_current_edition_command():
    edition = EditionFactory()
    call_command("set_current_edition", edition.code)
    assert Conference.objects.get().current_edition == edition
    with pytest.raises(CommandError):
        call_command("set_current_edition", "ZZ99")
