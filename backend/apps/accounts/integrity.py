"""Contrôles d'intégrité des comptes (plan L1 §8.4) : ce que MariaDB ne garantit pas.

Les contraintes d'unicité conditionnelles d'allauth (adresse vérifiée, un TOTP par
compte) ne sont pas créées sous MariaDB (W036) ; la cohérence entre invitations
acceptées et rôles relève des services. Messages sans donnée personnelle.
"""

from __future__ import annotations

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.db.models import Count
from django.db.models.functions import Lower

from apps.accounts.models import InvitationStatus, RoleInvitation, UserRole


def check_duplicate_verified_emails() -> list[str]:
    duplicates = (
        EmailAddress.objects.filter(verified=True)
        .annotate(normalized=Lower("email"))
        .values("normalized")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
        .count()
    )
    return [f"Adresses vérifiées en double : {duplicates}."] if duplicates else []


def check_duplicate_authenticators() -> list[str]:
    duplicates = (
        Authenticator.objects.filter(
            type__in=(Authenticator.Type.TOTP, Authenticator.Type.RECOVERY_CODES)
        )
        .values("user_id", "type")
        .annotate(count=Count("id"))
        .filter(count__gt=1)
    )
    users = sorted({row["user_id"] for row in duplicates})
    return [f"Authentificateurs 2FA en double (comptes #{users})."] if users else []


def check_invitations_and_roles() -> list[str]:
    problems: list[str] = []
    accepted = RoleInvitation.objects.filter(status=InvitationStatus.ACCEPTED).values_list(
        "id", "accepted_by_id", "edition_id", "role", "oc_function"
    )
    orphans = [
        invitation_id
        for invitation_id, user_id, edition_id, role, oc_function in accepted
        if user_id is None
        or not UserRole.objects.filter(
            user_id=user_id, edition_id=edition_id, role=role, oc_function=oc_function
        ).exists()
    ]
    if orphans:
        problems.append(f"Invitations acceptées sans rôle correspondant : {orphans}.")
    keys = (
        RoleInvitation.objects.exclude(status=InvitationStatus.PENDING)
        .filter(pending_key__isnull=False)
        .count()
        + RoleInvitation.objects.filter(
            status=InvitationStatus.PENDING, pending_key__isnull=True
        ).count()
    )
    if keys:
        problems.append(f"Clés d'unicité d'invitation incohérentes : {keys}.")
    return problems


def register_accounts_integrity_checks() -> None:
    from apps.core.integrity import register_integrity_check

    register_integrity_check("accounts.duplicate_verified_emails", check_duplicate_verified_emails)
    register_integrity_check("accounts.duplicate_authenticators", check_duplicate_authenticators)
    register_integrity_check("accounts.invitations_roles", check_invitations_and_roles)
