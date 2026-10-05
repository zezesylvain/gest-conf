"""Attribution et révocation des rôles par édition (plan L1 §5.5, §5.6, D7, RG-17).

Règles appliquées ici (défense en profondeur : aussi pour les commandes et les tâches) :
- matrice d'attribution (``GRANTORS``) pour une action venant d'un utilisateur ;
- on ne modifie jamais ses propres rôles ;
- le dernier ADMIN actif d'une édition ne se révoque que par commande (``last_admin``) ;
- toute révocation exige un motif ; une édition archivée est en lecture seule ;
- chaque attribution ou révocation est auditée et notifiée par e-mail au bénéficiaire.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import RoleSource, User, UserRole, UserRoleStatus
from apps.accounts.roles import OcFunction, Role
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.conferences.models import Edition
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation

if TYPE_CHECKING:
    from apps.accounts.services.access import EditionAccess

ROLE_GRANTED_TEMPLATE = "role/email/role_granted"
ROLE_REVOKED_TEMPLATE = "role/email/role_revoked"


def register_role_templates() -> None:
    register_email_template(ROLE_GRANTED_TEMPLATE, fast_path=True)
    register_email_template(ROLE_REVOKED_TEMPLATE, fast_path=True)


def check_oc_function(role: str, oc_function: str) -> None:
    """Fonction CO renseignée si et seulement si le rôle est OC_MEMBER (D8, CHECK en base)."""
    if role not in Role.values:
        raise Invalid(fields={"role": [_("Rôle inconnu.")]})
    if oc_function not in OcFunction.values:
        raise Invalid(fields={"oc_function": [_("Fonction inconnue.")]})
    if (role == Role.OC_MEMBER) != bool(oc_function):
        raise Invalid(
            fields={"oc_function": [_("Fonction obligatoire pour le CO, interdite sinon.")]}
        )


def ensure_editable(edition: Edition) -> None:
    """Une édition archivée est en lecture seule partout (409 ``edition_archived``, §6.3)."""
    if edition.is_archived:
        raise RuleViolation(_("Édition archivée : lecture seule."), code=ErrorCode.EDITION_ARCHIVED)


def check_can_manage(
    access: EditionAccess, role: str, *, target: User | None, actor: Actor
) -> None:
    """Matrice §5.5 et interdiction d'agir sur ses propres rôles, pour un utilisateur."""
    if role not in access.manageable_roles:
        raise NotAllowed(_("Vous ne pouvez pas attribuer ni retirer ce rôle."))
    if target is not None and actor.user is not None and target.pk == actor.user.pk:
        raise NotAllowed(_("Vous ne pouvez pas modifier vos propres rôles."))


def edition_title(edition: Edition, locale: str) -> str:
    """Titre de l'édition dans la langue demandée, français en repli (D14)."""
    return edition.title_en if locale == "en" and edition.title_en else edition.title_fr


def _notify(template: str, user_role: UserRole, *, reason: str = "") -> None:
    user = user_role.user
    locale = resolve_locale(None, user)
    edition = user_role.edition
    with translation.override(locale):
        context = {
            "edition_title": edition_title(edition, locale),
            "edition_code": edition.code,
            "role_label": str(Role(user_role.role).label),
            "reason": reason,
        }
    queue_email(
        template_code=template,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=context,
    )


@transaction.atomic
def grant_role(
    *,
    user: User,
    edition: Edition,
    role: str,
    actor: Actor,
    source: str,
    oc_function: str = "",
    invitation=None,
    reason: str = "",
) -> UserRole:
    """Attribue un rôle (idempotent : aucune nouvelle ligne si le rôle est déjà actif).

    Le contrôle de la matrice d'attribution est fait à l'émission de l'invitation ;
    l'attribution directe n'existe que par commande et par le système (AUTHOR, ATTENDEE).
    """
    check_oc_function(role, oc_function)
    if source not in RoleSource.values:
        raise ValueError(f"Origine de rôle inconnue : {source}")
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)
    existing = (
        UserRole.objects.select_for_update()
        .filter(user=user, edition=edition, role=role, oc_function=oc_function)
        .first()
    )
    now = timezone.now()
    # Par invitation : l'invitant (nul pour une invitation créée par commande).
    if invitation is not None:
        granted_by = invitation.invited_by
    else:
        granted_by = actor.user if actor.kind == ActorKind.USER else None
    if existing is not None and existing.status == UserRoleStatus.ACTIVE:
        return existing
    if existing is not None:
        before = snapshot(existing)
        existing.status = UserRoleStatus.ACTIVE
        existing.source = source
        existing.granted_at = now
        existing.granted_by = granted_by
        existing.revoked_at = None
        existing.revoked_by = None
        existing.revoke_reason = ""
        existing.invitation = invitation
        existing.save()
        user_role, action = existing, "role.reactivated"
    else:
        before = None
        user_role = UserRole.objects.create(
            user=user,
            edition=edition,
            role=role,
            oc_function=oc_function,
            source=source,
            granted_at=now,
            granted_by=granted_by,
            invitation=invitation,
        )
        action = "role.granted"
    record(
        action,
        actor=actor,
        edition=edition,
        obj=user_role,
        before=before,
        after=snapshot(user_role),
        reason=reason,
    )
    if source != RoleSource.SYSTEM:
        _notify(ROLE_GRANTED_TEMPLATE, user_role)
    return user_role


def active_admin_count(edition: Edition, *, lock: bool = False) -> int:
    """Nombre d'ADMIN actifs. ``lock`` : lecture verrouillante (dernier état validé, et non
    l'instantané de la transaction), à utiliser sous le verrou de l'édition."""
    queryset = UserRole.objects.filter(
        edition=edition, role=Role.ADMIN, status=UserRoleStatus.ACTIVE
    )
    if lock:
        return len(queryset.select_for_update().values_list("pk", flat=True))
    return queryset.count()


@transaction.atomic
def revoke_role(
    *,
    user_role: UserRole,
    actor: Actor,
    reason: str,
    access: EditionAccess | None = None,
) -> UserRole:
    """Révoque un rôle (motif obligatoire). ``access`` : droits de l'acteur utilisateur.

    Le verrou de l'édition, pris en premier, sérialise les révocations concurrentes : sans
    lui, deux ADMIN qui se révoquent l'un l'autre en même temps compteraient chacun deux
    ADMIN actifs, et l'édition n'en aurait plus aucun (``last_admin``).
    """
    list(Edition.objects.select_for_update().filter(pk=user_role.edition_id).values_list("pk"))
    user_role = (
        UserRole.objects.select_for_update().select_related("edition", "user").get(pk=user_role.pk)
    )
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    if actor.kind == ActorKind.USER:
        if access is None:
            raise NotAllowed()
        check_can_manage(access, user_role.role, target=user_role.user, actor=actor)
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(user_role.edition)
    if user_role.status == UserRoleStatus.REVOKED:
        return user_role
    if (
        user_role.role == Role.ADMIN
        and actor.kind != ActorKind.COMMAND
        and active_admin_count(user_role.edition, lock=True) <= 1
    ):
        raise RuleViolation(
            _("Le dernier administrateur de l'édition ne se retire que par commande."),
            code=ErrorCode.LAST_ADMIN,
        )
    before = snapshot(user_role)
    user_role.status = UserRoleStatus.REVOKED
    user_role.revoked_at = timezone.now()
    user_role.revoked_by = actor.user if actor.kind == ActorKind.USER else None
    user_role.revoke_reason = reason
    user_role.save()
    record(
        "role.revoked",
        actor=actor,
        edition=user_role.edition,
        obj=user_role,
        before=before,
        after=snapshot(user_role),
        reason=reason,
    )
    _notify(ROLE_REVOKED_TEMPLATE, user_role, reason=reason)
    return user_role
