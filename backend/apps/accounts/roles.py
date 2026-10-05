"""Rôles par édition, capacités et matrice d'attribution (plan L1 §5.2, §5.5, D3, D7, D8).

**Source unique, codée et revue en PR**, jamais paramétrable en base (§5.1). Le serveur
calcule les droits à partir de *tous* les rôles actifs de l'utilisateur dans l'édition
visée ; il ne lit jamais de « rôle actif » envoyé par le client (règles n° 2 et 5).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum

from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    """Les 11 rôles de l'étude (§3.2), toujours rattachés à une édition."""

    ADMIN = "ADMIN", _("administrateur de l'édition")
    CHAIR = "CHAIR", _("président de la conférence")
    OC_MEMBER = "OC_MEMBER", _("membre du comité d'organisation")
    SC_CHAIR = "SC_CHAIR", _("président du comité scientifique")
    SC_MEMBER = "SC_MEMBER", _("membre du comité scientifique")
    AUTHOR = "AUTHOR", _("auteur")
    SPEAKER = "SPEAKER", _("intervenant")
    SESSION_CHAIR = "SESSION_CHAIR", _("président de session")
    ATTENDEE = "ATTENDEE", _("participant")
    SPONSOR = "SPONSOR", _("partenaire")
    VOLUNTEER = "VOLUNTEER", _("bénévole")


class OcFunction(models.TextChoices):
    """Fonction au comité d'organisation (union des listes §3.1 et M8, D8) ; vide hors CO."""

    NONE = "", _("aucune")
    FINANCE = "finance", _("finances")
    PROGRAM = "program", _("programme")
    LOGISTICS = "logistics", _("logistique")
    COMMUNICATION = "communication", _("communication")
    EXTERNAL_RELATIONS = "external_relations", _("relations extérieures")
    VOLUNTEERS = "volunteers", _("bénévoles")
    SECRETARIAT = "secretariat", _("secrétariat")


class InvitableRole(models.TextChoices):
    """Rôles qu'une invitation peut attribuer en L1 (§3.3) ; les autres dans leur lot."""

    ADMIN = Role.ADMIN.value, Role.ADMIN.label
    CHAIR = Role.CHAIR.value, Role.CHAIR.label
    SC_CHAIR = Role.SC_CHAIR.value, Role.SC_CHAIR.label
    OC_MEMBER = Role.OC_MEMBER.value, Role.OC_MEMBER.label
    SC_MEMBER = Role.SC_MEMBER.value, Role.SC_MEMBER.label


class Capability(StrEnum):
    EDITION_READ = "edition.read"
    EDITION_WRITE = "edition.write"
    EDITION_PUBLISH = "edition.publish"
    EDITION_ARCHIVE = "edition.archive"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    AUDIT_READ = "audit.read"


C = Capability

# Jeu de choix exposé dans le schéma OpenAPI (énumération « Capability »).
CAPABILITY_CHOICES: list[tuple[str, str]] = [(item.value, item.value) for item in Capability]

# Table rôles → capacités (§5.2). SC_CHAIR : lecture du paramétrage (D8, validée) et
# gestion des membres limitée au comité scientifique (voir MANAGEABLE_ROLES).
CAPABILITIES: Mapping[str, frozenset[Capability]] = {
    Role.ADMIN: frozenset(C),
    Role.CHAIR: frozenset(
        {
            C.EDITION_READ,
            C.EDITION_WRITE,
            C.EDITION_PUBLISH,
            C.MEMBERS_READ,
            C.MEMBERS_MANAGE,
            C.AUDIT_READ,
        }
    ),
    Role.SC_CHAIR: frozenset({C.EDITION_READ, C.MEMBERS_READ, C.MEMBERS_MANAGE}),
    # CO en lecture seule en L1, quelle que soit sa fonction (D8) ; écritures partielles
    # attribuées fonction par fonction dans leur lot (programme L5, finances L6).
    Role.OC_MEMBER: frozenset({C.EDITION_READ}),
    Role.SC_MEMBER: frozenset(),
    Role.AUTHOR: frozenset(),
    Role.SPEAKER: frozenset(),
    Role.SESSION_CHAIR: frozenset(),
    Role.ATTENDEE: frozenset(),
    Role.SPONSOR: frozenset(),
    Role.VOLUNTEER: frozenset(),
}

# 2FA imposée côté serveur à l'accès aux routes de gestion d'une édition (D3).
# SC_MEMBER : à trancher avant L4 (une ligne à ajouter).
MFA_REQUIRED_ROLES: frozenset[str] = frozenset(
    {Role.ADMIN, Role.CHAIR, Role.SC_CHAIR, Role.OC_MEMBER}
)

# Matrice d'attribution (§5.5) : rôle visé → rôles qui peuvent l'attribuer (et révoquer).
# L'opérateur (commande) peut tout attribuer ; AUTHOR et ATTENDEE : système seulement.
GRANTORS: Mapping[str, frozenset[str]] = {
    Role.ADMIN: frozenset({Role.ADMIN}),
    Role.CHAIR: frozenset({Role.ADMIN}),
    Role.SC_CHAIR: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.OC_MEMBER: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.SC_MEMBER: frozenset({Role.ADMIN, Role.CHAIR, Role.SC_CHAIR}),
    # Activés dans leur lot (L5, L8).
    Role.SPEAKER: frozenset(),
    Role.SESSION_CHAIR: frozenset(),
    Role.SPONSOR: frozenset(),
    Role.VOLUNTEER: frozenset(),
    Role.AUTHOR: frozenset(),
    Role.ATTENDEE: frozenset(),
}

# Attribution d'ADMIN ou de CHAIR : réauthentification récente exigée (§5.5).
REAUTH_REQUIRED_FOR_GRANT: frozenset[str] = frozenset({Role.ADMIN, Role.CHAIR})

# Rôles du comité scientifique, seuls visibles du SC_CHAIR dans les membres (§5.4).
SCIENTIFIC_COMMITTEE: frozenset[str] = frozenset({Role.SC_CHAIR, Role.SC_MEMBER})


def capabilities_for(roles: Iterable[str]) -> frozenset[Capability]:
    result: set[Capability] = set()
    for role in roles:
        result |= CAPABILITIES[role]
    return frozenset(result)


def manageable_roles(roles: Iterable[str]) -> frozenset[str]:
    """Rôles que les détenteurs de ``roles`` peuvent attribuer ou révoquer."""
    held = set(roles)
    return frozenset(target for target, grantors in GRANTORS.items() if grantors & held)


def visible_member_roles(roles: Iterable[str]) -> frozenset[str] | None:
    """Rôles visibles dans les listes de membres et d'invitations ; ``None`` = tous.

    ADMIN et CHAIR voient tout ; le SC_CHAIR seul ne voit que le comité scientifique,
    sinon il verrait les adresses invitées aux rôles ADMIN, CHAIR et CO (§5.4).
    """
    held = set(roles)
    if held & {Role.ADMIN, Role.CHAIR}:
        return None
    if Role.SC_CHAIR in held:
        return SCIENTIFIC_COMMITTEE
    return frozenset()
