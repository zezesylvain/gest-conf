"""Invitations aux rôles de comité (plan L1 §5.7, D6) et règle RG-20.

**RG-20 (proposée, validée avec D6).** Une invitation ne s'accepte que depuis un compte
qui **contrôle l'adresse invitée** : une adresse vérifiée du compte correspond, ou la
personne la rattache par un lien de liaison envoyé à cette adresse (option (a) de D6).
Le jeton d'invitation seul ne suffit jamais : sinon un lien transféré ou retrouvé dans
un historique deviendrait un titre au porteur pour le rôle.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, models, transaction
from django.http import Http404
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import (
    MESSAGE_MAX_LENGTH,
    InvitationStatus,
    Profile,
    RoleInvitation,
    RoleSource,
    User,
    UserRole,
    UserRoleStatus,
)
from apps.accounts.notifications import notify_email_added
from apps.accounts.roles import InvitableRole, Role
from apps.accounts.services.roles import (
    check_can_manage,
    check_oc_function,
    edition_title,
    ensure_editable,
    grant_role,
)
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.core.actor import Actor
from apps.core.audit import mask_email, record, snapshot
from apps.core.errors import ErrorCode, Invalid, NotAllowed, QuotaExceeded, RuleViolation

if TYPE_CHECKING:
    from apps.accounts.services.access import EditionAccess
    from apps.conferences.models import Edition

INVITATION_TEMPLATE = "role/email/invitation"
INVITATION_LINK_TEMPLATE = "role/email/invitation_link"

INVITATION_VALIDITY = timedelta(days=14)
MAX_EMAILS_PER_REQUEST = 50
# Quota d'adresses invitées par heure et par invitant (§4.7) : ScopedRateThrottle compte
# des requêtes, or une requête peut porter 50 adresses (hameçonnage depuis le domaine).
HOURLY_ADDRESS_QUOTA = 100
MAX_SENDS = 3
LINK_SALT = "gestconf.invitation-link"
LINK_MAX_AGE = 3600


def register_invitation_templates() -> None:
    # Liens à jeton : corps purgés à l'envoi ; voie rapide (au plus 3 par requête, §8.3) :
    # envoyés par un membre authentifié, quelle que soit l'existence d'un compte.
    register_email_template(INVITATION_TEMPLATE, sensitive=True, fast_path=True)
    register_email_template(INVITATION_LINK_TEMPLATE, sensitive=True, fast_path=True)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pending_key(edition_id: int, email: str, role: str, oc_function: str) -> str:
    """Empreinte de longueur fixe : aucune troncature ni erreur 1406, quelle que soit
    la longueur de l'adresse (§3.1)."""
    return hashlib.sha256(f"{edition_id}:{email}:{role}:{oc_function}".encode()).hexdigest()


def normalize_email(email: str) -> str:
    return User.objects.normalize_email(email)


def display_name(user: User | None) -> str:
    """Nom affiché (profil), sinon adresse masquée ; jamais l'adresse en clair à un tiers.

    Pour une liste, charger le profil avec ``select_related("…__profile")`` (pas de N+1).
    """
    if user is None:
        return ""
    try:
        profile = user.profile
    except Profile.DoesNotExist:
        profile = None
    if profile is not None and (profile.first_name or profile.last_name):
        return f"{profile.first_name} {profile.last_name}".strip()
    return mask_email(user.email)


def _invite_url(token: str) -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}/compte/invitation#{token}"


def _send_invitation(invitation: RoleInvitation, token: str) -> None:
    locale = invitation.locale
    with translation.override(locale):
        context = {
            "invite_url": _invite_url(token),
            "edition_title": edition_title(invitation.edition, locale),
            "edition_code": invitation.edition.code,
            "role_label": str(Role(invitation.role).label),
            "inviter_name": display_name(invitation.invited_by),
            "message": invitation.message,
            "expires_on": invitation.expires_at.date().isoformat(),
        }
    queue_email(
        template_code=INVITATION_TEMPLATE,
        to_email=invitation.email,
        locale=locale,
        context=context,
    )


def _expire(invitation: RoleInvitation, actor: Actor) -> None:
    before = snapshot(invitation)
    invitation.status = InvitationStatus.EXPIRED
    invitation.pending_key = None
    invitation.save(update_fields=["status", "pending_key", "updated_at"])
    record(
        "invitation.expired",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        before=before,
        after=snapshot(invitation),
    )


# --- Création -------------------------------------------------------------------------------


class SkippedReason(models.TextChoices):
    ALREADY_PENDING = "already_pending", _("invitation déjà en attente")
    ALREADY_MEMBER = "already_member", _("rôle déjà actif")


@dataclass
class InvitationBatch:
    created: list[RoleInvitation] = field(default_factory=list)
    # (adresse masquée, code) : already_pending, already_member.
    skipped: list[tuple[str, str]] = field(default_factory=list)


def _check_quota(inviter: User | None, count: int, now: datetime) -> None:
    if inviter is None:
        return
    window = RoleInvitation.objects.filter(
        invited_by=inviter, created_at__gte=now - timedelta(hours=1)
    )
    if window.count() + count > HOURLY_ADDRESS_QUOTA:
        oldest = window.order_by("created_at").values_list("created_at", flat=True).first()
        retry_after = ((oldest or now) + timedelta(hours=1) - now).total_seconds()
        raise QuotaExceeded(
            _("Quota d'invitations atteint pour cette heure."), retry_after=max(retry_after, 1)
        )


def _clean_emails(emails: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    errors: list[str] = []
    for raw in emails:
        email = normalize_email(raw)
        try:
            validate_email(email)
        except ValidationError:
            errors.append(str(_("Adresse invalide : %(email)s") % {"email": raw}))
            continue
        if email not in cleaned:
            cleaned.append(email)
    if errors:
        raise Invalid(fields={"emails": errors})
    if not cleaned:
        raise Invalid(fields={"emails": [_("Au moins une adresse.")]})
    if len(cleaned) > MAX_EMAILS_PER_REQUEST:
        raise Invalid(
            fields={"emails": [_("%(max)s adresses au plus.") % {"max": MAX_EMAILS_PER_REQUEST}]}
        )
    return cleaned


def _has_active_role(edition: Edition, email: str, role: str, oc_function: str) -> bool:
    owners = EmailAddress.objects.filter(email__iexact=email, verified=True).values("user_id")
    return UserRole.objects.filter(
        edition=edition,
        role=role,
        oc_function=oc_function,
        status=UserRoleStatus.ACTIVE,
        user_id__in=owners,
    ).exists()


@transaction.atomic
def create_invitations(
    *,
    edition: Edition,
    emails: Iterable[str],
    role: str,
    actor: Actor,
    access: EditionAccess | None,
    oc_function: str = "",
    locale: str | None = None,
    message: str = "",
) -> InvitationBatch:
    """Invite des adresses à un rôle (50 au plus par appel, 100 par heure et par invitant).

    ``access`` : droits de l'invitant (matrice §5.5) ; ``None`` pour une commande
    (``create_edition --admin-email``). Audit ``invitation.created``, sans adresse en clair.
    """
    ensure_editable(edition)
    if role not in InvitableRole.values:
        raise Invalid(fields={"role": [_("Rôle non invitable.")]})
    check_oc_function(role, oc_function)
    if access is not None:
        check_can_manage(access, role, target=None, actor=actor)
    if len(message) > MESSAGE_MAX_LENGTH:
        raise Invalid(fields={"message": [_("1 000 caractères au plus.")]})
    addresses = _clean_emails(emails)
    now = timezone.now()
    inviter = actor.user
    _check_quota(inviter, len(addresses), now)
    resolved_locale = resolve_locale(locale, None)

    batch = InvitationBatch()
    for email in addresses:
        key = pending_key(edition.pk, email, role, oc_function)
        # Expiration à la volée : une invitation échue ne bloque pas une nouvelle (§3.3).
        for overdue in RoleInvitation.objects.select_for_update().filter(
            pending_key=key, expires_at__lte=now
        ):
            _expire(overdue, actor)
        if _has_active_role(edition, email, role, oc_function):
            batch.skipped.append((mask_email(email), SkippedReason.ALREADY_MEMBER))
            continue
        token = secrets.token_urlsafe(32)
        try:
            with transaction.atomic():
                invitation = RoleInvitation.objects.create(
                    edition=edition,
                    email=email,
                    role=role,
                    oc_function=oc_function,
                    token_hash=token_hash(token),
                    pending_key=key,
                    invited_by=inviter,
                    expires_at=now + INVITATION_VALIDITY,
                    locale=resolved_locale,
                    message=message,
                    last_sent_at=now,
                )
        except IntegrityError:
            # Une invitation identique est déjà en attente (unicité de pending_key).
            batch.skipped.append((mask_email(email), SkippedReason.ALREADY_PENDING))
            continue
        record(
            "invitation.created",
            actor=actor,
            edition=edition,
            obj=invitation,
            after=snapshot(invitation),
        )
        _send_invitation(invitation, token)
        batch.created.append(invitation)
    return batch


# --- Consultation, acceptation, refus ----------------------------------------------------


def find_by_token(token: str, *, for_update: bool = False) -> RoleInvitation:
    if not isinstance(token, str) or not token:
        raise Http404
    queryset = RoleInvitation.objects.select_related("edition", "invited_by")
    if for_update:
        queryset = queryset.select_for_update()
    invitation = queryset.filter(token_hash=token_hash(token)).first()
    if invitation is None:
        raise Http404
    return invitation


def _ensure_pending(invitation: RoleInvitation) -> None:
    """Invitation en attente et non échue ; une invitation échue est passée en ``expired``
    par la création suivante (même clé) ou par ``cleanup``."""
    expired_by_date = (
        invitation.status == InvitationStatus.PENDING and invitation.expires_at <= timezone.now()
    )
    if expired_by_date or invitation.status == InvitationStatus.EXPIRED:
        raise RuleViolation(_("Invitation expirée."), code=ErrorCode.INVITATION_EXPIRED)
    if invitation.status != InvitationStatus.PENDING:
        raise RuleViolation(
            _("Cette invitation n'est plus en attente."), code=ErrorCode.INVITATION_NOT_PENDING
        )


def _controls_address(user: User, email: str) -> bool:
    return EmailAddress.objects.filter(user=user, email__iexact=email, verified=True).exists()


def _verified_elsewhere(user: User, email: str) -> bool:
    return (
        EmailAddress.objects.filter(email__iexact=email, verified=True).exclude(user=user).exists()
    )


def lookup(token: str, user: User | None) -> dict[str, Any]:
    """Informations affichées avant d'accepter ou de refuser (adresse masquée, §5.7)."""
    invitation = find_by_token(token)
    status = invitation.status
    if status == InvitationStatus.PENDING and invitation.expires_at <= timezone.now():
        status = InvitationStatus.EXPIRED
    authenticated = user is not None and user.is_authenticated
    return {
        "edition_code": invitation.edition.code,
        "edition_title_fr": invitation.edition.title_fr,
        "edition_title_en": invitation.edition.title_en,
        "role": invitation.role,
        "oc_function": invitation.oc_function,
        "inviter_name": display_name(invitation.invited_by),
        "email_masked": mask_email(invitation.email),
        "status": status,
        "expires_at": invitation.expires_at,
        "message": invitation.message,
        "controls_address": authenticated and _controls_address(user, invitation.email),
    }


def _accept(invitation: RoleInvitation, user: User, actor: Actor) -> UserRole:
    before = snapshot(invitation)
    invitation.status = InvitationStatus.ACCEPTED
    invitation.pending_key = None
    invitation.responded_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(
        update_fields=["status", "pending_key", "responded_at", "accepted_by", "updated_at"]
    )
    user_role = grant_role(
        user=user,
        edition=invitation.edition,
        role=invitation.role,
        oc_function=invitation.oc_function,
        actor=actor,
        source=RoleSource.INVITATION,
        invitation=invitation,
    )
    record(
        "invitation.accepted",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        before=before,
        after=snapshot(invitation),
    )
    return user_role


def _check_not_inviter(invitation: RoleInvitation, user: User) -> None:
    """On ne s'attribue jamais un rôle (§5.5) : ferme le scénario « s'inviter à sa propre
    adresse puis la lier à son compte » (plan v3)."""
    if invitation.invited_by_id is not None and invitation.invited_by_id == user.pk:
        raise NotAllowed(
            _("Vous ne pouvez pas accepter une invitation que vous avez envoyée."),
            code=ErrorCode.INVITATION_SELF_ACCEPT,
        )


@transaction.atomic
def accept(token: str, *, user: User, actor: Actor) -> UserRole:
    """Acceptation par jeton (RG-20, cas a) ; cas b et c refusés en 409."""
    invitation = find_by_token(token, for_update=True)
    _ensure_pending(invitation)
    _check_not_inviter(invitation, user)
    ensure_editable(invitation.edition)
    if _controls_address(user, invitation.email):
        return _accept(invitation, user, actor)
    if _verified_elsewhere(user, invitation.email):
        raise RuleViolation(
            _("Connectez-vous avec le compte qui porte l'adresse invitée."),
            code=ErrorCode.INVITATION_EMAIL_MISMATCH,
        )
    raise RuleViolation(
        _("Votre compte ne contrôle pas l'adresse invitée : liez-la d'abord à votre compte."),
        code=ErrorCode.INVITATION_EMAIL_UNVERIFIED,
    )


@transaction.atomic
def decline(token: str, *, actor: Actor) -> RoleInvitation:
    """Refus : ne donne aucun droit, donc sans compte (§5.7). Nouvelle invitation possible."""
    invitation = find_by_token(token, for_update=True)
    _ensure_pending(invitation)
    before = snapshot(invitation)
    invitation.status = InvitationStatus.DECLINED
    invitation.pending_key = None
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "pending_key", "responded_at", "updated_at"])
    record(
        "invitation.declined",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        before=before,
        after=snapshot(invitation),
    )
    return invitation


# --- Liaison de l'adresse invitée (RG-20, cas c ; option (a) de D6) ---------------------


def make_link_token(invitation: RoleInvitation, user: User) -> str:
    return signing.dumps({"i": invitation.pk, "u": user.pk}, salt=LINK_SALT)


def _link_invalid() -> Invalid:
    return Invalid(_("Lien invalide ou expiré."), code=ErrorCode.INVITATION_LINK_INVALID)


@transaction.atomic
def request_email_link(token: str, *, user: User, actor: Actor) -> RoleInvitation:
    """Envoie à l'adresse invitée un lien signé, lié au compte demandeur (valable 1 h).

    Réauthentification récente exigée par la vue (``RecentAuthRequired``).
    """
    invitation = find_by_token(token, for_update=True)
    _ensure_pending(invitation)
    _check_not_inviter(invitation, user)
    if _verified_elsewhere(user, invitation.email):
        raise RuleViolation(
            _("Connectez-vous avec le compte qui porte l'adresse invitée."),
            code=ErrorCode.INVITATION_EMAIL_MISMATCH,
        )
    locale = resolve_locale(None, user)
    queue_email(
        template_code=INVITATION_LINK_TEMPLATE,
        to_email=invitation.email,
        locale=locale,
        context={
            "link_url": (
                f"{settings.GESTCONF_PUBLIC_URL}/compte/invitation"
                f"#lier={make_link_token(invitation, user)}"
            ),
            "edition_code": invitation.edition.code,
        },
    )
    record(
        "invitation.link_requested",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        after={"email_masked": mask_email(invitation.email)},
    )
    return invitation


@transaction.atomic
def accept_with_link(link: str, *, user: User, actor: Actor) -> UserRole:
    """Ajoute l'adresse invitée au compte (vérifiée) puis accepte l'invitation.

    Mêmes protections que l'ajout d'adresse par allauth tel que configuré (§4.2) :
    réauthentification récente (vue), limite de 3 adresses, refus d'une adresse vérifiée
    sur un autre compte, notification à l'adresse principale. Une seule transaction.
    """
    try:
        data = signing.loads(link, salt=LINK_SALT, max_age=LINK_MAX_AGE)
    except signing.BadSignature as exc:  # SignatureExpired en hérite
        raise _link_invalid() from exc
    if not isinstance(data, dict) or data.get("u") != user.pk:
        raise _link_invalid()
    invitation = (
        RoleInvitation.objects.select_for_update()
        .select_related("edition", "invited_by")
        .filter(pk=data.get("i"))
        .first()
    )
    if invitation is None:
        raise _link_invalid()
    _ensure_pending(invitation)
    _check_not_inviter(invitation, user)
    ensure_editable(invitation.edition)
    if _verified_elsewhere(user, invitation.email):
        raise RuleViolation(
            _("Cette adresse est déjà vérifiée sur un autre compte."),
            code=ErrorCode.INVITATION_EMAIL_MISMATCH,
        )
    address = EmailAddress.objects.filter(user=user, email__iexact=invitation.email).first()
    if address is None:
        if not EmailAddress.objects.can_add_email(user):
            raise RuleViolation(
                _("Votre compte porte déjà le nombre maximal d'adresses."),
                code=ErrorCode.EMAIL_ADDRESS_LIMIT,
            )
        EmailAddress.objects.create(user=user, email=invitation.email, verified=True, primary=False)
        linked = True
    elif not address.verified:
        address.verified = True
        address.save(update_fields=["verified"])
        linked = True
    else:
        linked = False
    if linked:
        record(
            "account.email_linked",
            actor=actor,
            edition=invitation.edition,
            obj=user,
            after={"email_masked": mask_email(invitation.email)},
        )
        notify_email_added(user, invitation.email, actor=actor)
    return _accept(invitation, user, actor)


# --- Gestion par les membres : renvoi, annulation, expiration ----------------------------


def _check_manageable(invitation: RoleInvitation, access: EditionAccess, actor: Actor) -> None:
    check_can_manage(access, invitation.role, target=None, actor=actor)


@transaction.atomic
def resend(invitation: RoleInvitation, *, actor: Actor, access: EditionAccess) -> RoleInvitation:
    """Renvoie l'invitation avec un nouveau jeton (l'ancien lien devient invalide)."""
    invitation = (
        RoleInvitation.objects.select_for_update()
        .select_related("edition", "invited_by")
        .get(pk=invitation.pk)
    )
    _check_manageable(invitation, access, actor)
    ensure_editable(invitation.edition)
    _ensure_pending(invitation)
    if invitation.send_count >= MAX_SENDS:
        raise RuleViolation(
            _("Nombre maximal de renvois atteint."), code=ErrorCode.INVITATION_RESEND_LIMIT
        )
    before = snapshot(invitation)
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    invitation.token_hash = token_hash(token)
    invitation.send_count += 1
    invitation.last_sent_at = now
    invitation.expires_at = now + INVITATION_VALIDITY
    invitation.save(
        update_fields=["token_hash", "send_count", "last_sent_at", "expires_at", "updated_at"]
    )
    record(
        "invitation.resent",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        before=before,
        after=snapshot(invitation),
    )
    _send_invitation(invitation, token)
    return invitation


@transaction.atomic
def cancel(invitation: RoleInvitation, *, actor: Actor, access: EditionAccess) -> RoleInvitation:
    invitation = (
        RoleInvitation.objects.select_for_update().select_related("edition").get(pk=invitation.pk)
    )
    _check_manageable(invitation, access, actor)
    ensure_editable(invitation.edition)
    if invitation.status != InvitationStatus.PENDING:
        raise RuleViolation(
            _("Cette invitation n'est plus en attente."), code=ErrorCode.INVITATION_NOT_PENDING
        )
    before = snapshot(invitation)
    invitation.status = InvitationStatus.CANCELLED
    invitation.pending_key = None
    invitation.responded_at = timezone.now()
    invitation.save(update_fields=["status", "pending_key", "responded_at", "updated_at"])
    record(
        "invitation.cancelled",
        actor=actor,
        edition=invitation.edition,
        obj=invitation,
        before=before,
        after=snapshot(invitation),
    )
    return invitation


def expire_due_invitations(dry_run: bool, now: datetime) -> int:
    """Tâche de ``cleanup`` : passe en ``expired`` les invitations échues (§8.4)."""
    due = RoleInvitation.objects.filter(status=InvitationStatus.PENDING, expires_at__lte=now)
    if dry_run:
        return due.count()
    actor = Actor.system("cron:cleanup")
    count = 0
    for invitation in due.select_related("edition"):
        with transaction.atomic():
            _expire(invitation, actor)
        count += 1
    return count


def pending_for_user(user: User) -> list[RoleInvitation]:
    """Invitations en attente adressées aux adresses vérifiées du compte (``/v1/me``)."""
    emails = list(
        EmailAddress.objects.filter(user=user, verified=True).values_list("email", flat=True)
    )
    if not emails:
        return []
    return list(
        RoleInvitation.objects.filter(
            email__in=[normalize_email(email) for email in emails],
            status=InvitationStatus.PENDING,
            expires_at__gt=timezone.now(),
        )
        .select_related("edition")
        .order_by("-created_at")
    )
