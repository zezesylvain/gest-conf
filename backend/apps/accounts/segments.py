"""Segments des envois groupés fondés sur les rôles de l'édition (plan L8, N11)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRoleStatus
from apps.accounts.roles import Role


def _holders(*roles: str):
    def query(edition):
        return User.objects.filter(
            roles__edition=edition, roles__status=UserRoleStatus.ACTIVE, roles__role__in=roles
        )

    return query


def register_accounts_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(
        Segment("speakers.invited", _("Intervenants invités"), _holders(Role.SPEAKER), 60)
    )
    register_segment(
        Segment(
            "committees.scientific",
            _("Comité scientifique"),
            _holders(Role.SC_CHAIR, Role.SC_MEMBER),
            70,
        )
    )
    register_segment(
        Segment(
            "committees.organising",
            _("Comité d'organisation"),
            _holders(Role.ADMIN, Role.CHAIR, Role.OC_MEMBER),
            71,
        )
    )
    register_segment(Segment("volunteers", _("Bénévoles"), _holders(Role.VOLUNTEER), 80))
