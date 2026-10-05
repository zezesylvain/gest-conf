"""Export et anonymisation d'un compte (plan L1 §4.9, RG-18, D15).

``export_user_data`` et ``anonymize_user`` parcourent le registre
``apps.core.personal_data`` : chaque application y déclare ses traitements. Les
traitements de ``accounts`` sont définis ici et enregistrés par ``AccountsConfig``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import (
    Consent,
    InvitationStatus,
    Profile,
    RoleInvitation,
    User,
    UserRole,
    UserRoleStatus,
)
from apps.accounts.roles import Role
from apps.accounts.services.account import PROFILE_FIELDS, delete_user_sessions
from apps.conferences.models import EditionStatus
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.personal_data import (
    AnonymizationContext,
    anonymize_sections,
    export_sections,
)

EXPORT_FORMAT = "gestconf-export-v1"
ANONYMIZED_DOMAIN = "anonymized.invalid"
ANONYMIZATION_REASON = "anonymisation du compte"
# Rôles qui ne sont pas des responsabilités à transmettre avant l'anonymisation (D15).
NON_DUTY_ROLES = frozenset({Role.AUTHOR, Role.ATTENDEE})
# D15 (non validée) : invitations traitées dont l'adresse et le message sont effacés.
INVITATION_REDACT_AFTER = timedelta(days=365)
# D15 (non validée) : IP des consentements effacée après 6 mois.
CONSENT_NETWORK_RETENTION = timedelta(days=183)


def anonymized_email(user: User) -> str:
    return f"anonymized-{user.pk}@{ANONYMIZED_DOMAIN}"


# --- Export --------------------------------------------------------------------------------


def export_user_data(user: User, *, actor: Actor) -> dict[str, Any]:
    """Toutes les données du compte, sans aucun secret (plan §4.9). Audit ``account.exported``."""
    data = {
        "format": EXPORT_FORMAT,
        "generated_at": timezone.now().isoformat(),
        **export_sections(user),
    }
    record("account.exported", actor=actor, obj=user, after={"sections": sorted(data)})
    return data


def _export_account(user: User) -> dict[str, Any]:
    profile = Profile.objects.filter(user=user).first()
    authenticators = Authenticator.objects.filter(user=user).order_by("id")
    return {
        "account": {
            "id": user.pk,
            "email": user.email,
            "locale": user.locale,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
        "profile": {name: getattr(profile, name) for name in PROFILE_FIELDS} if profile else {},
        "email_addresses": [
            {"email": item.email, "verified": item.verified, "primary": item.primary}
            for item in EmailAddress.objects.filter(user=user).order_by("id")
        ],
        # État de la 2FA seulement : jamais le secret ni les codes de secours.
        "mfa": [
            {
                "type": item.type,
                "created_at": item.created_at.isoformat(),
                "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
            }
            for item in authenticators
        ],
    }


def _export_consents(user: User) -> dict[str, Any]:
    return {
        "consents": [
            {
                "kind": item.kind,
                "granted": item.granted,
                "text_version": item.text_version,
                "source": item.source,
                "recorded_at": item.recorded_at.isoformat(),
            }
            for item in Consent.objects.filter(user=user).order_by("recorded_at", "id")
        ]
    }


def _export_roles(user: User) -> dict[str, Any]:
    roles = UserRole.objects.filter(user=user).select_related("edition").order_by("id")
    return {
        "roles": [
            {
                "edition": item.edition.code,
                "role": item.role,
                "oc_function": item.oc_function,
                "status": item.status,
                "granted_at": item.granted_at.isoformat(),
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
            }
            for item in roles
        ]
    }


def _received_invitations(user: User):
    emails = list(EmailAddress.objects.filter(user=user).values_list("email", flat=True))
    queryset = RoleInvitation.objects.filter(accepted_by=user)
    for email in {user.email, *emails}:
        queryset = queryset | RoleInvitation.objects.filter(email__iexact=email)
    return queryset.distinct()


def _export_invitations(user: User) -> dict[str, Any]:
    invitations = _received_invitations(user).select_related("edition").order_by("id")
    return {
        "invitations": [
            {
                "edition": item.edition.code,
                "email": item.email,
                "role": item.role,
                "status": item.status,
                "message": item.message,
                "created_at": item.created_at.isoformat(),
                "responded_at": item.responded_at.isoformat() if item.responded_at else None,
            }
            for item in invitations
        ]
    }


# --- Anonymisation -----------------------------------------------------------------------


def active_duties(user: User) -> list[str]:
    """Responsabilités à transmettre avant l'anonymisation (plan §4.9) : rôle actif autre
    qu'auteur ou participant dans une édition non archivée, ou dernier ADMIN d'une édition."""
    from apps.accounts.services.roles import active_admin_count

    duties: list[str] = []
    active = UserRole.objects.filter(user=user, status=UserRoleStatus.ACTIVE).select_related(
        "edition"
    )
    for item in active:
        if item.role in NON_DUTY_ROLES:
            continue
        if item.edition.status != EditionStatus.ARCHIVED or (
            item.role == Role.ADMIN and active_admin_count(item.edition) <= 1
        ):
            duties.append(f"{item.edition.code}:{item.role}")
    return sorted(set(duties))


@transaction.atomic
def anonymize_user(user: User, *, actor: Actor, reason: str = "") -> User:
    """Anonymise le compte dans une seule transaction (plan §4.9, RG-18).

    Refusée (``account_has_active_duties``) tant que la personne détient des
    responsabilités. Le journal d'audit et les consentements sont conservés comme preuves
    (D15) ; leurs IP sont effacées. Audit ``account.anonymized`` sans donnée personnelle.
    """
    user = User.objects.select_for_update().get(pk=user.pk)
    if user.anonymized_at is not None:
        return user
    if actor.kind == ActorKind.COMMAND and not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    duties = active_duties(user)
    if duties:
        raise RuleViolation(
            _("Transmettez d'abord vos rôles de gestion actifs."),
            code=ErrorCode.ACCOUNT_HAS_ACTIVE_DUTIES,
            fields={"roles": duties},
        )
    profile = Profile.objects.filter(user=user).first()
    names = {
        value.strip()
        for value in (
            profile.first_name if profile else "",
            profile.last_name if profile else "",
            f"{profile.first_name} {profile.last_name}" if profile else "",
        )
        if len(value.strip()) >= 3
    }
    emails = {user.email.lower()} | {
        email.lower()
        for email in EmailAddress.objects.filter(user=user).values_list("email", flat=True)
    }
    context = AnonymizationContext(
        actor=actor,
        anonymized_email=anonymized_email(user),
        original_emails=frozenset(emails),
        names=frozenset(names),
    )
    anonymize_sections(user, context)
    record("account.anonymized", actor=actor, obj=user, reason=reason)
    return user


def _anonymize_consents(user: User, context: AnonymizationContext) -> None:
    Consent.redact_network_for_user(user, actor=context.actor)


def _anonymize_roles(user: User, context: AnonymizationContext) -> None:
    now = timezone.now()
    UserRole.objects.filter(user=user, status=UserRoleStatus.ACTIVE).update(
        status=UserRoleStatus.REVOKED,
        revoked_at=now,
        revoke_reason=ANONYMIZATION_REASON,
        updated_at=now,
    )


def _anonymize_invitations(user: User, context: AnonymizationContext) -> None:
    """Invitations reçues (à l'une de ses adresses, ou acceptées) : adresse anonymisée et
    message vidé, quel que soit le statut ; celles en attente sont annulées. Invitations
    envoyées : message vidé (il porte souvent la signature de l'invitant)."""
    now = timezone.now()
    received = RoleInvitation.objects.filter(accepted_by=user)
    for email in context.original_emails:
        received = received | RoleInvitation.objects.filter(email__iexact=email)
    received_ids = list(received.values_list("id", flat=True))
    RoleInvitation.objects.filter(pk__in=received_ids, status=InvitationStatus.PENDING).update(
        status=InvitationStatus.CANCELLED, pending_key=None, responded_at=now
    )
    RoleInvitation.objects.filter(pk__in=received_ids).update(
        email=context.anonymized_email, message="", updated_at=now
    )
    RoleInvitation.objects.filter(invited_by=user).update(message="", updated_at=now)


def _anonymize_account(user: User, context: AnonymizationContext) -> None:
    """Dernier traitement : profil vidé, adresses et 2FA supprimées, sessions fermées,
    compte désactivé avec une adresse anonyme et un mot de passe inutilisable."""
    Profile.objects.filter(user=user).update(**dict.fromkeys(PROFILE_FIELDS, ""))
    Authenticator.objects.filter(user=user).delete()
    EmailAddress.objects.filter(user=user).delete()
    delete_user_sessions(user)
    user.email = context.anonymized_email
    user.set_unusable_password()
    user.is_active = False
    user.anonymized_at = timezone.now()
    user.save(update_fields=["email", "password", "is_active", "anonymized_at", "updated_at"])


# --- Conservation (D15, simulation tant que les durées ne sont pas validées) ------------


def redact_old_invitations(dry_run: bool, now: datetime) -> int:
    """Invitations expirées, refusées ou annulées depuis plus de 12 mois : adresse et
    message effacés (D15)."""
    old = RoleInvitation.objects.filter(
        status__in=(
            InvitationStatus.EXPIRED,
            InvitationStatus.DECLINED,
            InvitationStatus.CANCELLED,
        ),
        updated_at__lt=now - INVITATION_REDACT_AFTER,
    ).exclude(email__endswith=f"@{ANONYMIZED_DOMAIN}")
    if dry_run:
        return old.count()
    count = 0
    for invitation in old.only("id"):
        RoleInvitation.objects.filter(pk=invitation.pk).update(
            email=f"redacted-invitation-{invitation.pk}@{ANONYMIZED_DOMAIN}", message=""
        )
        count += 1
    return count


def purge_consent_network(dry_run: bool, now: datetime) -> int:
    date = now - CONSENT_NETWORK_RETENTION
    if dry_run:
        return Consent.objects.filter(recorded_at__lt=date, ip__isnull=False).count()
    return Consent.purge_network_before(date, actor=Actor.system("cron:cleanup"))


def register_accounts_personal_data() -> None:
    from apps.core.personal_data import register_personal_data

    register_personal_data(
        "accounts.consents",
        models=("accounts.Consent",),
        export=_export_consents,
        anonymize=_anonymize_consents,
    )
    register_personal_data(
        "accounts.roles",
        models=("accounts.UserRole",),
        export=_export_roles,
        anonymize=_anonymize_roles,
    )
    register_personal_data(
        "accounts.invitations",
        models=("accounts.RoleInvitation",),
        export=_export_invitations,
        anonymize=_anonymize_invitations,
    )
    # Le compte en dernier : les autres traitements lisent encore ses adresses.
    register_personal_data(
        "accounts.account",
        models=("accounts.User", "accounts.Profile", "account.EmailAddress", "mfa.Authenticator"),
        export=_export_account,
        anonymize=_anonymize_account,
        rank=1000,
    )
