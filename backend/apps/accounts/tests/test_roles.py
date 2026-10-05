"""Rôles par édition (plan L1 §5.2, §5.5, §5.6, §12.1 « Rôles » ; RG-17)."""

import pytest
from django.core import mail
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts.models import RoleSource, UserRole, UserRoleStatus
from apps.accounts.roles import (
    CAPABILITIES,
    GRANTORS,
    MFA_REQUIRED_ROLES,
    Capability,
    OcFunction,
    Role,
    manageable_roles,
)
from apps.accounts.services.access import edition_access
from apps.accounts.services.roles import grant_role, revoke_role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, NotAllowed, RuleViolation
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")
SYSTEM = Actor.system("job:test")


def user_actor(user):
    return Actor(kind=ActorKind.USER, user=user)


# --- Tables (source unique, revue en PR) ----------------------------------------------


def test_capabilities_table_covers_every_role():
    assert set(CAPABILITIES) == set(Role.values)
    assert set(GRANTORS) == set(Role.values)


def test_mfa_required_roles_match_d3():
    assert {Role.ADMIN, Role.CHAIR, Role.SC_CHAIR, Role.OC_MEMBER} == MFA_REQUIRED_ROLES


@pytest.mark.parametrize(
    ("grantor", "expected"),
    [
        (Role.ADMIN, {Role.ADMIN, Role.CHAIR, Role.SC_CHAIR, Role.OC_MEMBER, Role.SC_MEMBER}),
        (Role.CHAIR, {Role.SC_CHAIR, Role.OC_MEMBER, Role.SC_MEMBER}),
        (Role.SC_CHAIR, {Role.SC_MEMBER}),
        (Role.OC_MEMBER, set()),
        (Role.SC_MEMBER, set()),
        (Role.AUTHOR, set()),
    ],
)
def test_grantors_table(grantor, expected):
    """§5.5 : AUTHOR et ATTENDEE ne sont jamais attribués à la main."""
    assert manageable_roles([grantor]) == expected


def test_edition_access_in_one_query():
    edition = EditionFactory()
    user = make_member(edition, Role.CHAIR)
    UserRole.objects.create(
        user=user,
        edition=edition,
        role=Role.SC_MEMBER,
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )
    with CaptureQueriesContext(connection) as queries:
        access = edition_access(user, edition.pk)
        assert access.edition.code == edition.code
        assert access.has(Capability.EDITION_PUBLISH)
    assert len(queries) == 1


# --- grant_role -----------------------------------------------------------------------------


def test_rg17_grant_role_is_idempotent_with_one_audit_entry():
    """§5.6 : une seule ligne et une seule entrée d'audit, même appelé deux fois."""
    edition = EditionFactory()
    user = VerifiedUserFactory()
    for _ in range(2):
        grant_role(
            user=user, edition=edition, role=Role.AUTHOR, actor=SYSTEM, source=RoleSource.SYSTEM
        )
    assert UserRole.objects.filter(user=user).count() == 1
    assert AuditLog.objects.filter(action="role.granted").count() == 1
    # Attribution système : pas de notification.
    assert mail.outbox == []


def test_rg17_role_grant_and_revoke_logged_with_before_after(django_capture_on_commit_callbacks):
    edition = EditionFactory()
    user = VerifiedUserFactory()
    user_role = grant_role(
        user=user, edition=edition, role=Role.SC_MEMBER, actor=COMMAND, source=RoleSource.COMMAND
    )
    revoke_role(user_role=user_role, actor=COMMAND, reason="Fin de mandat")
    granted = AuditLog.objects.get(action="role.granted")
    revoked = AuditLog.objects.get(action="role.revoked")
    assert granted.edition == edition
    assert granted.before is None
    assert granted.after["status"] == "active"
    assert (revoked.before["status"], revoked.after["status"]) == ("active", "revoked")
    assert revoked.reason == "Fin de mandat"
    assert revoked.actor_kind == "command"
    # Le bénéficiaire est prévenu de chaque attribution et révocation (§5.5).
    from apps.communications.models import OutboxEmail

    templates = list(OutboxEmail.objects.values_list("template_code", flat=True))
    assert templates == ["role/email/role_granted", "role/email/role_revoked"]


def test_reactivation_reuses_the_row():
    edition = EditionFactory()
    user = VerifiedUserFactory()
    user_role = grant_role(
        user=user, edition=edition, role=Role.SC_MEMBER, actor=COMMAND, source=RoleSource.COMMAND
    )
    revoke_role(user_role=user_role, actor=COMMAND, reason="x")
    again = grant_role(
        user=user, edition=edition, role=Role.SC_MEMBER, actor=COMMAND, source=RoleSource.COMMAND
    )
    assert again.pk == user_role.pk
    assert again.status == UserRoleStatus.ACTIVE
    assert AuditLog.objects.filter(action="role.reactivated").count() == 1


@pytest.mark.parametrize(
    ("role", "oc_function"),
    [
        (Role.OC_MEMBER, ""),
        (Role.SC_MEMBER, OcFunction.FINANCE),
        ("ROI", ""),
        (Role.OC_MEMBER, "chef"),
    ],
)
def test_oc_function_consistency(role, oc_function):
    with pytest.raises(Invalid):
        grant_role(
            user=VerifiedUserFactory(),
            edition=EditionFactory(),
            role=role,
            oc_function=oc_function,
            actor=COMMAND,
            source=RoleSource.COMMAND,
        )


def test_two_oc_functions_for_the_same_person():
    """D6 : une personne peut avoir deux fonctions au CO."""
    edition = EditionFactory()
    user = VerifiedUserFactory()
    for function in (OcFunction.FINANCE, OcFunction.LOGISTICS):
        grant_role(
            user=user,
            edition=edition,
            role=Role.OC_MEMBER,
            oc_function=function,
            actor=COMMAND,
            source=RoleSource.COMMAND,
        )
    assert UserRole.objects.filter(user=user, role=Role.OC_MEMBER).count() == 2


# --- revoke_role ----------------------------------------------------------------------------


def test_last_admin_cannot_be_revoked():
    """§5.5 : le dernier ADMIN actif ne se révoque que par commande (``last_admin``).

    Par l'API, le cas n'arrive qu'en concurrence (on ne retire jamais son propre rôle, et
    un autre ADMIN actif fait deux ADMIN) : l'accès de l'acteur est donc simulé.
    """
    from apps.accounts.services.access import EditionAccess

    edition = EditionFactory()
    admin = make_member(edition, Role.ADMIN)
    former_admin = VerifiedUserFactory()
    stale_access = EditionAccess(edition=edition, roles=frozenset({(Role.ADMIN, "")}))
    last = UserRole.objects.get(user=admin)
    with pytest.raises(RuleViolation) as error:
        revoke_role(user_role=last, actor=user_actor(former_admin), reason="x", access=stale_access)
    assert error.value.code == "last_admin"
    revoke_role(user_role=last, actor=COMMAND, reason="Passation")
    assert UserRole.objects.get(pk=last.pk).status == UserRoleStatus.REVOKED


def test_admin_can_revoke_another_admin_but_chair_cannot():
    edition = EditionFactory()
    first, second = make_member(edition, Role.ADMIN), make_member(edition, Role.ADMIN)
    chair = make_member(edition, Role.CHAIR)
    target = UserRole.objects.get(user=first)
    with pytest.raises(NotAllowed):
        revoke_role(
            user_role=target,
            actor=user_actor(chair),
            reason="x",
            access=edition_access(chair, edition.pk),
        )
    revoke_role(
        user_role=target,
        actor=user_actor(second),
        reason="x",
        access=edition_access(second, edition.pk),
    )
    assert UserRole.objects.get(pk=target.pk).status == UserRoleStatus.REVOKED


def test_revocation_requires_reason():
    edition = EditionFactory()
    user_role = UserRole.objects.get(user=make_member(edition, Role.SC_MEMBER))
    with pytest.raises(Invalid):
        revoke_role(user_role=user_role, actor=COMMAND, reason="  ")


def test_cannot_change_own_roles():
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    UserRole.objects.create(
        user=chair,
        edition=edition,
        role=Role.SC_MEMBER,
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )
    own = UserRole.objects.get(user=chair, role=Role.SC_MEMBER)
    with pytest.raises(NotAllowed):
        revoke_role(
            user_role=own,
            actor=user_actor(chair),
            reason="x",
            access=edition_access(chair, edition.pk),
        )


def test_archived_edition_refuses_role_changes_except_by_command():
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    with pytest.raises(RuleViolation):
        grant_role(
            user=VerifiedUserFactory(),
            edition=edition,
            role=Role.AUTHOR,
            actor=SYSTEM,
            source=RoleSource.SYSTEM,
        )
    grant_role(
        user=VerifiedUserFactory(),
        edition=edition,
        role=Role.SC_MEMBER,
        actor=COMMAND,
        source=RoleSource.COMMAND,
    )


# --- Contraintes en base (MariaDB fait foi) ---------------------------------------------


@pytest.mark.mariadb
def test_userrole_oc_function_check_constraint():
    edition = EditionFactory()
    user = VerifiedUserFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        UserRole.objects.create(
            user=user,
            edition=edition,
            role=Role.SC_MEMBER,
            oc_function=OcFunction.FINANCE,
            source=RoleSource.COMMAND,
            granted_at=timezone.now(),
        )
    with pytest.raises(IntegrityError), transaction.atomic():
        UserRole.objects.create(
            user=user,
            edition=edition,
            role=Role.OC_MEMBER,
            source=RoleSource.COMMAND,
            granted_at=timezone.now(),
        )


@pytest.mark.mariadb
def test_userrole_unique_with_oc_function():
    edition = EditionFactory()
    user = make_member(edition, Role.SC_MEMBER)
    with pytest.raises(IntegrityError), transaction.atomic():
        UserRole.objects.create(
            user=user,
            edition=edition,
            role=Role.SC_MEMBER,
            source=RoleSource.COMMAND,
            granted_at=timezone.now(),
        )


@pytest.mark.mariadb_only  # SQLite verrouille la base entière : sans objet
@pytest.mark.django_db(transaction=True)
def test_concurrent_admin_revocations_keep_one_admin():
    """§5.5 : deux ADMIN qui se révoquent l'un l'autre en même temps. Le verrou de l'édition
    sérialise les deux transactions : la seconde voit le dernier état validé et reçoit
    ``last_admin`` ; l'édition garde un administrateur."""
    import threading
    import time

    from django.db import connection as default_connection

    edition = EditionFactory()
    first, second = make_member(edition, Role.ADMIN), make_member(edition, Role.ADMIN)
    accesses = {user.pk: edition_access(user, edition.pk) for user in (first, second)}
    roles = {user.pk: UserRole.objects.get(user=user) for user in (first, second)}
    first_holds_lock = threading.Event()
    errors: list[str] = []

    def revoke(actor_user, target_user, *, hold: bool) -> None:
        try:
            with transaction.atomic():
                revoke_role(
                    user_role=roles[target_user.pk],
                    actor=user_actor(actor_user),
                    reason="x",
                    access=accesses[actor_user.pk],
                )
                if hold:
                    first_holds_lock.set()
                    time.sleep(0.5)
        except RuleViolation as error:
            errors.append(error.code)
        finally:
            default_connection.close()

    one = threading.Thread(target=revoke, args=(first, second), kwargs={"hold": True})
    one.start()
    assert first_holds_lock.wait(5)
    two = threading.Thread(target=revoke, args=(second, first), kwargs={"hold": False})
    two.start()
    one.join(10)
    two.join(10)
    assert errors == ["last_admin"]
    assert (
        UserRole.objects.filter(
            edition=edition, role=Role.ADMIN, status=UserRoleStatus.ACTIVE
        ).count()
        == 1
    )
