"""Comptes et clients de test par rôle (matrice des droits, plan L1 §5.9)."""

from __future__ import annotations

import time

from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.models import RoleSource, UserRole, UserRoleStatus
from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.factories import VerifiedUserFactory

AUTH_RECORDS = "account_authentication_methods"


def make_member(edition, role: str, *, status: str = UserRoleStatus.ACTIVE, **user_fields):
    user = VerifiedUserFactory(**user_fields)
    UserRole.objects.create(
        user=user,
        edition=edition,
        role=role,
        oc_function=OcFunction.FINANCE if role == Role.OC_MEMBER else "",
        status=status,
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )
    return user


def client_for(user, *, recent_auth: bool = True) -> APIClient:
    """Client connecté par une vraie session, avec horodatage de connexion (D12) et, si
    demandé, une authentification récente (``RecentAuthRequired``, §4.5)."""
    client = APIClient()
    client.force_login(user)
    session = client.session
    session[LOGIN_AT_SESSION_KEY] = time.time()
    at = time.time() if recent_auth else time.time() - 3600
    session[AUTH_RECORDS] = [{"method": "password", "at": at, "email": user.email}]
    session.save()
    return client
