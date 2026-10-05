"""Droits d'un compte dans une édition (plan L1 §5.1, §5.3)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.http import Http404

from apps.accounts.models import UserRole, UserRoleStatus
from apps.accounts.roles import (
    MFA_REQUIRED_ROLES,
    Capability,
    capabilities_for,
    manageable_roles,
    visible_member_roles,
)

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.conferences.models import Edition


@dataclass(frozen=True, slots=True)
class EditionAccess:
    """Rôles actifs et capacités d'un compte dans une édition, calculés côté serveur."""

    edition: Edition
    roles: frozenset[tuple[str, str]]  # (rôle, fonction CO)

    @property
    def role_names(self) -> frozenset[str]:
        return frozenset(role for role, _function in self.roles)

    @property
    def capabilities(self) -> frozenset[Capability]:
        return capabilities_for(self.role_names)

    def has(self, capability: Capability) -> bool:
        return capability in self.capabilities

    @property
    def mfa_required(self) -> bool:
        return bool(self.role_names & MFA_REQUIRED_ROLES)

    @property
    def manageable_roles(self) -> frozenset[str]:
        return manageable_roles(self.role_names)

    @property
    def visible_roles(self) -> frozenset[str] | None:
        """Rôles visibles dans les membres et invitations (``None`` = tous)."""
        return visible_member_roles(self.role_names)


def active_roles(user: User, edition_id: int):
    return UserRole.objects.filter(user=user, edition_id=edition_id, status=UserRoleStatus.ACTIVE)


def edition_access(user: User, edition_id: int) -> EditionAccess:
    """Accès de ``user`` à l'édition, en **une** requête ; ``Http404`` sans rôle actif.

    404 et non 403 : un non-membre n'apprend pas l'existence d'une édition, même en
    brouillon (D5).
    """
    rows = list(active_roles(user, edition_id).select_related("edition"))
    if not rows:
        raise Http404
    return EditionAccess(
        edition=rows[0].edition,
        roles=frozenset((row.role, row.oc_function) for row in rows),
    )


def editions_with_roles(user: User) -> dict[int, EditionAccess]:
    """Accès du compte à chacune des éditions où il a un rôle actif (``/v1/me``, sélecteur)."""
    grouped: dict[int, tuple[Edition, set[tuple[str, str]]]] = {}
    rows = (
        UserRole.objects.filter(user=user, status=UserRoleStatus.ACTIVE)
        .select_related("edition")
        .order_by("-edition__year", "edition_id")
    )
    for row in rows:
        _edition, roles = grouped.setdefault(row.edition_id, (row.edition, set()))
        roles.add((row.role, row.oc_function))
    return {
        edition_id: EditionAccess(edition=edition, roles=frozenset(roles))
        for edition_id, (edition, roles) in grouped.items()
    }
