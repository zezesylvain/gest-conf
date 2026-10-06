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
    """Rôles qu'une invitation peut attribuer (§3.3) : ceux de L1, puis intervenants et
    présidents de séance en L5 (I10) ; les autres dans leur lot."""

    ADMIN = Role.ADMIN.value, Role.ADMIN.label
    CHAIR = Role.CHAIR.value, Role.CHAIR.label
    SC_CHAIR = Role.SC_CHAIR.value, Role.SC_CHAIR.label
    OC_MEMBER = Role.OC_MEMBER.value, Role.OC_MEMBER.label
    SC_MEMBER = Role.SC_MEMBER.value, Role.SC_MEMBER.label
    SPEAKER = Role.SPEAKER.value, Role.SPEAKER.label
    SESSION_CHAIR = Role.SESSION_CHAIR.value, Role.SESSION_CHAIR.label


class Capability(StrEnum):
    EDITION_READ = "edition.read"
    EDITION_WRITE = "edition.write"
    EDITION_PUBLISH = "edition.publish"
    EDITION_ARCHIVE = "edition.archive"
    MEMBERS_READ = "members.read"
    MEMBERS_MANAGE = "members.manage"
    AUDIT_READ = "audit.read"
    # Lot L2 (E11) : contenus du portail (sections, pages, menus).
    PORTAL_WRITE = "portal.write"
    # Lot L3 (F8, F10) : soumissions dans la gestion (lecture, dérogations, export).
    SUBMISSIONS_READ = "submissions.read"
    SUBMISSIONS_EXTEND = "submissions.extend"
    SUBMISSIONS_EXPORT = "submissions.export"
    # Lot L4 (H19) : évaluation et décision.
    REVIEWS_WRITE = "reviews.write"  # évaluer ses affectations (relecteur)
    REVIEWS_MANAGE = "reviews.manage"  # recevabilité, affectations, conflits, suivi
    REVIEWS_READ_ALL = "reviews.read_all"  # évaluations de tous les relecteurs
    DECISIONS_DECIDE = "decisions.decide"
    DECISIONS_PUBLISH = "decisions.publish"
    GRIDS_WRITE = "grids.write"
    # Lot L5 (I1) : programme (brouillon lu par les comités, écrit par le CO « programme »,
    # publié par le Chair).
    PROGRAM_READ = "program.read"
    PROGRAM_WRITE = "program.write"
    PROGRAM_PUBLISH = "program.publish"
    # Lot L6 (J1) : inscriptions (lues par le CO, gérées par les finances et le secrétariat),
    # tarifs (finances), paiements et factures (finances, Chair en lecture).
    REGISTRATIONS_READ = "registrations.read"
    REGISTRATIONS_MANAGE = "registrations.manage"
    PRICING_WRITE = "pricing.write"
    FINANCE_READ = "finance.read"


C = Capability

# Jeu de choix exposé dans le schéma OpenAPI (énumération « Capability »).
CAPABILITY_CHOICES: list[tuple[str, str]] = [(item.value, item.value) for item in Capability]

# Table rôles → capacités (§5.2). SC_CHAIR : lecture du paramétrage (D8, validée) et
# gestion des membres limitée au comité scientifique (voir MANAGEABLE_ROLES).
CAPABILITIES: Mapping[str, frozenset[Capability]] = {
    # ADMIN administre l'édition ; il n'évalue pas et ne décide pas (H19) ; il ne publie pas
    # le programme, que le Chair valide (I1, étude §5.4).
    Role.ADMIN: frozenset(C)
    - {C.REVIEWS_WRITE, C.DECISIONS_DECIDE, C.DECISIONS_PUBLISH, C.PROGRAM_PUBLISH},
    Role.CHAIR: frozenset(
        {
            C.EDITION_READ,
            C.EDITION_WRITE,
            C.EDITION_PUBLISH,
            C.MEMBERS_READ,
            C.MEMBERS_MANAGE,
            C.AUDIT_READ,
            C.PORTAL_WRITE,
            C.SUBMISSIONS_READ,
            C.SUBMISSIONS_EXTEND,
            C.SUBMISSIONS_EXPORT,
            C.REVIEWS_MANAGE,
            C.REVIEWS_READ_ALL,
            C.DECISIONS_DECIDE,
            C.DECISIONS_PUBLISH,
            C.GRIDS_WRITE,
            # I1 : le Chair lit et valide (publie) le programme ; il ne l'écrit pas.
            C.PROGRAM_READ,
            C.PROGRAM_PUBLISH,
            # J1 (plan L6) : il suit les inscriptions et les finances, sans les gérer.
            C.REGISTRATIONS_READ,
            C.FINANCE_READ,
        }
    ),
    # Président du CS : il peut aussi évaluer (H19).
    Role.SC_CHAIR: frozenset(
        {
            C.EDITION_READ,
            C.MEMBERS_READ,
            C.MEMBERS_MANAGE,
            C.SUBMISSIONS_READ,
            C.SUBMISSIONS_EXTEND,
            C.SUBMISSIONS_EXPORT,
            C.REVIEWS_WRITE,
            C.REVIEWS_MANAGE,
            C.REVIEWS_READ_ALL,
            C.DECISIONS_DECIDE,
            C.DECISIONS_PUBLISH,
            C.GRIDS_WRITE,
            C.PROGRAM_READ,
        }
    ),
    # CO en lecture seule en L1, quelle que soit sa fonction (D8) ; écritures partielles
    # attribuées fonction par fonction dans leur lot (FUNCTION_CAPABILITIES). Lecture des
    # soumissions, identité des auteurs comprise (F10, matrice §3.3 de l'étude), du
    # programme brouillon (I1) et des inscriptions (J1, plan L6).
    Role.OC_MEMBER: frozenset(
        {C.EDITION_READ, C.SUBMISSIONS_READ, C.PROGRAM_READ, C.REGISTRATIONS_READ}
    ),
    # Relecteur : ses affectations seulement, sans identité des auteurs (RG-04, H9).
    Role.SC_MEMBER: frozenset({C.REVIEWS_WRITE}),
    Role.AUTHOR: frozenset(),
    Role.SPEAKER: frozenset(),
    Role.SESSION_CHAIR: frozenset(),
    Role.ATTENDEE: frozenset(),
    Role.SPONSOR: frozenset(),
    Role.VOLUNTEER: frozenset(),
}

# 2FA imposée côté serveur à l'accès aux routes de gestion d'une édition (D3). SC_MEMBER
# depuis L4 (H2) : un relecteur lit des travaux inédits.
MFA_REQUIRED_ROLES: frozenset[str] = frozenset(
    {Role.ADMIN, Role.CHAIR, Role.SC_CHAIR, Role.OC_MEMBER, Role.SC_MEMBER}
)

# Matrice d'attribution (§5.5) : rôle visé → rôles qui peuvent l'attribuer (et révoquer).
# L'opérateur (commande) peut tout attribuer ; AUTHOR et ATTENDEE : système seulement.
GRANTORS: Mapping[str, frozenset[str]] = {
    Role.ADMIN: frozenset({Role.ADMIN}),
    Role.CHAIR: frozenset({Role.ADMIN}),
    Role.SC_CHAIR: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.OC_MEMBER: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.SC_MEMBER: frozenset({Role.ADMIN, Role.CHAIR, Role.SC_CHAIR}),
    # I10 (plan L5) : intervenants invités et présidents de séance, invités par les
    # détenteurs de ``members.manage`` de l'édition. Sponsors et bénévoles : lot L8.
    Role.SPEAKER: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.SESSION_CHAIR: frozenset({Role.ADMIN, Role.CHAIR}),
    Role.SPONSOR: frozenset(),
    Role.VOLUNTEER: frozenset(),
    Role.AUTHOR: frozenset(),
    Role.ATTENDEE: frozenset(),
}

# Attribution d'ADMIN ou de CHAIR : réauthentification récente exigée (§5.5).
REAUTH_REQUIRED_FOR_GRANT: frozenset[str] = frozenset({Role.ADMIN, Role.CHAIR})

# Rôles du comité scientifique, seuls visibles du SC_CHAIR dans les membres (§5.4).
SCIENTIFIC_COMMITTEE: frozenset[str] = frozenset({Role.SC_CHAIR, Role.SC_MEMBER})


# Capacités ajoutées par la fonction au comité d'organisation (rôle, fonction) → capacités.
# E11 (plan L2) : le CO « communication » rédige les contenus du portail ; I1 (plan L5) : le CO
# « programme » écrit le programme ; J1 (plan L6) : le CO « finances » gère inscriptions,
# tarifs et finances, le « secrétariat » les inscriptions. Les autres fonctions reçoivent leurs
# écritures dans leur lot.
FUNCTION_CAPABILITIES: Mapping[tuple[str, str], frozenset[Capability]] = {
    (Role.OC_MEMBER, "communication"): frozenset({C.PORTAL_WRITE}),
    # I1 (plan L5) : le CO « programme » écrit le programme ; les autres fonctions le lisent.
    (Role.OC_MEMBER, "program"): frozenset({C.PROGRAM_WRITE}),
    (Role.OC_MEMBER, "finance"): frozenset(
        {C.REGISTRATIONS_MANAGE, C.PRICING_WRITE, C.FINANCE_READ}
    ),
    (Role.OC_MEMBER, "secretariat"): frozenset({C.REGISTRATIONS_MANAGE}),
}


def capabilities_for(roles: Iterable[str]) -> frozenset[Capability]:
    """Capacités des rôles seuls, sans tenir compte des fonctions au CO."""
    result: set[Capability] = set()
    for role in roles:
        result |= CAPABILITIES[role]
    return frozenset(result)


def capabilities_for_assignments(assignments: Iterable[tuple[str, str]]) -> frozenset[Capability]:
    """Capacités de couples (rôle, fonction au CO) : rôles, puis ajouts par fonction."""
    assignments = list(assignments)
    result = set(capabilities_for(role for role, _function in assignments))
    for assignment in assignments:
        result |= FUNCTION_CAPABILITIES.get(assignment, frozenset())
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
