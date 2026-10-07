"""Segment des envois groupés : présents (plan L8, N11 ; pointage de L7)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


def present(edition):
    """Comptes dont une inscription a un pointage non annulé (accueil ou session)."""
    from apps.events.models import Checkin

    registrations = Checkin.objects.filter(edition=edition, active_key__isnull=False).values(
        "registration__user_id"
    )
    return User.objects.filter(pk__in=registrations)


def register_events_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(Segment("attendees.present", _("Présents à la conférence"), present, 50))
