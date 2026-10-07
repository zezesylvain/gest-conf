"""Segments des envois groupés : inscrits (plan L8, N11)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.registrations.models import RegistrationStatus


def _registered(status: str):
    def query(edition):
        return User.objects.filter(registrations__edition=edition, registrations__status=status)

    return query


def register_registrations_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(
        Segment(
            "registrations.confirmed",
            _("Inscrits confirmés"),
            _registered(RegistrationStatus.CONFIRMED),
            40,
        )
    )
    register_segment(
        Segment(
            "registrations.pending",
            _("Inscrits en attente de paiement"),
            _registered(RegistrationStatus.PENDING),
            41,
        )
    )
