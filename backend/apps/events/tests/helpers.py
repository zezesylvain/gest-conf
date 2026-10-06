"""Données de test du jour J (plan L7)."""

from __future__ import annotations

from apps.accounts.models import Profile
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_registration


def participant(first="Awa", last="Diallo", **profile):
    user = VerifiedUserFactory()
    profile.setdefault("institution", "Université de Dakar")
    profile.setdefault("country", "SN")
    Profile.objects.create(user=user, first_name=first, last_name=last, **profile)
    return user


def confirmed(edition, user=None, **fields):
    return make_registration(
        edition, user or participant(), status=RegistrationStatus.CONFIRMED, **fields
    )
