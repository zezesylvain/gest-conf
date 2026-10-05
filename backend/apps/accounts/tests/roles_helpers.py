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
# Secret TOTP de test (base32), jamais utilisé ailleurs.
TEST_TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def make_member(
    edition,
    role: str,
    *,
    status: str = UserRoleStatus.ACTIVE,
    oc_function: str | None = None,
    **user_fields,
):
    user = VerifiedUserFactory(**user_fields)
    if oc_function is None:
        oc_function = OcFunction.FINANCE if role == Role.OC_MEMBER else ""
    UserRole.objects.create(
        user=user,
        edition=edition,
        role=role,
        oc_function=oc_function,
        status=status,
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )
    return user


def enable_totp(user, secret: str = TEST_TOTP_SECRET):
    """Active la 2FA TOTP du compte (secret chiffré par l'adaptateur, comme allauth)."""
    from allauth.mfa.models import Authenticator
    from allauth.mfa.utils import encrypt

    authenticator, _created = Authenticator.objects.get_or_create(
        user=user, type=Authenticator.Type.TOTP, defaults={"data": {"secret": encrypt(secret)}}
    )
    return authenticator


def client_for(user, *, recent_auth: bool = True, mfa: bool = True) -> APIClient:
    """Client connecté par une vraie session, avec horodatage de connexion (D12), une
    authentification récente si demandé (``RecentAuthRequired``, §4.5) et, par défaut,
    une 2FA activée et validée dans la session (``MfaVerified``, §4.4)."""
    client = APIClient()
    client.force_login(user)
    session = client.session
    session[LOGIN_AT_SESSION_KEY] = time.time()
    at = time.time() if recent_auth else time.time() - 3600
    records = [{"method": "password", "at": at, "email": user.email}]
    if mfa:
        authenticator = enable_totp(user)
        records.insert(0, {"method": "mfa", "at": at, "id": authenticator.pk, "type": "totp"})
    session[AUTH_RECORDS] = records
    session.save()
    return client
