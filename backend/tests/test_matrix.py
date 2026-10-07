"""Matrice des droits des routes de gestion (plan L1 §5.9, étude §3.3 ; règles n° 2 et 5).

Un test par case : ``test_matrix[<route>-<méthode>-<profil>-<statut>]``. Les capacités
attendues de chaque profil sont recopiées **à la main** du tableau §5.2 du plan
(``SPEC``), et non lues dans ``apps.accounts.roles`` : la matrice teste le code contre
la spécification, pas contre lui-même. 2FA (``mfa_*``) : cases ajoutées en L1.6.
"""

from __future__ import annotations

import datetime as dt
import functools
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import InvitationStatus, RoleInvitation, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.invitations import pending_key, token_hash
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import (
    EditionFactory,
    KeyDateFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from apps.core import public_files
from apps.core.models import PublicFileKind
from apps.portal.models import MenuItem, Page, PageSection, Section

pytestmark = pytest.mark.django_db

# --- Spécification (§5.2), recopiée à la main --------------------------------------------

R, W, PUB, ARC = "edition.read", "edition.write", "edition.publish", "edition.archive"
MR, MM, AR = "members.read", "members.manage", "audit.read"
PW = "portal.write"
SR, SE, SX = "submissions.read", "submissions.extend", "submissions.export"
# Plan L4 (H19) : évaluer, piloter l'évaluation, lire toutes les évaluations, décider, publier,
# écrire les grilles.
RW, RM, RA = "reviews.write", "reviews.manage", "reviews.read_all"
DD, DP, GW = "decisions.decide", "decisions.publish", "grids.write"
# Plan L5 (I1) : programme lu par les comités, écrit par le CO « programme » et
# l'administrateur, publié par le Chair.
PGR, PGW, PGP = "program.read", "program.write", "program.publish"
# Plan L6 (J1) : inscriptions lues par le CO et le Chair, gérées par les finances et le
# secrétariat ; tarifs par les finances ; paiements et factures lus par les finances et le Chair.
RGR, RGM = "registrations.read", "registrations.manage"
PRW, FIR = "pricing.write", "finance.read"
# Plan L7 (K1, K18) : pointer (bénévoles, tout le CO, administrateur) ; gérer les pointages
# (secrétariat, logistique, bénévoles) ; attestations (Chair, secrétariat) ; lettres
# d'invitation (secrétariat, relations extérieures) ; signature (le signataire seul).
CKS, CKM = "checkin.scan", "checkin.manage"
CEM, LEM, SGM = "certificates.manage", "letters.manage", "signature.manage"
# Plan L8 (N2) : tâches (CO, Chair), budget (finances ; Chair en lecture), partenaires
# (relations extérieures ; finances, communication et Chair en lecture), logistique
# (logistique ; secrétariat et Chair en lecture), planning des bénévoles (bénévoles,
# logistique), le sien (bénévole), annonces et envois groupés (communication, Chair),
# questionnaires (communication, secrétariat, Chair).
TKR, TKW = "tasks.read", "tasks.write"
BGR, BGW = "budget.read", "budget.write"
SPR, SPW = "sponsors.read", "sponsors.write"
LGR, LGW = "logistics.read", "logistics.write"
VLP, SHO = "volunteers.plan", "shifts.own"
CMS, SVM = "communications.send", "surveys.manage"
L8_TEAM = {TKR, TKW}

SPEC: dict[str, set[str]] = {
    # H19 : l'administrateur n'évalue pas et ne décide pas ; I1 : il ne publie pas le
    # programme. J1 : toutes les capacités des inscriptions et des finances.
    # K18 : il ne renseigne pas la signature d'un signataire.
    "ADMIN": {R, W, PUB, ARC, MR, MM, AR, PW, SR, SE, SX, RM, RA, GW, PGR, PGW, RGR, RGM}
    | {PRW, FIR, CKS, CKM, CEM, LEM}
    | L8_TEAM
    | {BGR, BGW, SPR, SPW, LGR, LGW, VLP, CMS, SVM},
    # I1 : le Chair lit et publie le programme, sans l'écrire. J1 : il lit les inscriptions
    # et les finances, sans les gérer. K1 : il émet les attestations, ne pointe pas.
    "CHAIR": {R, W, PUB, MR, MM, AR, PW, SR, SE, SX, RM, RA, DD, DP, GW, PGR, PGP, RGR, FIR}
    | {CEM}
    | L8_TEAM
    | {BGR, SPR, LGR, CMS, SVM},
    # D8 validée : lecture du paramétrage ; membres du CS seulement. F10, F8 (plan L3) :
    # soumissions (lecture, dérogations, export). H19 : évalue, pilote, décide, publie.
    # I1 : lit le programme. J1 : aucun accès aux inscriptions.
    "SC_CHAIR": {R, MR, MM, SR, SE, SX, RW, RM, RA, DD, DP, GW, PGR},
    # D8 : lecture seule (fonction « logistique ») ; F10 : soumissions ; I1 : programme lu ;
    # J1 : inscriptions lues. K1 (plan L7) : tout le CO pointe ; la logistique gère les
    # pointages.
    "OC_MEMBER": {R, SR, PGR, RGR, CKS, CKM} | L8_TEAM | {LGR, LGW, VLP},
    # E11 (plan L2) : le CO « communication » écrit le portail.
    "OC_COMMUNICATION": {R, PW, SR, PGR, RGR, CKS} | L8_TEAM | {SPR, CMS, SVM},
    # I1 (plan L5) : le CO « programme » écrit le programme.
    "OC_PROGRAM": {R, SR, PGR, PGW, RGR, CKS} | L8_TEAM,
    # J1 (plan L6) : le CO « finances » gère inscriptions, tarifs et finances ; le
    # « secrétariat » gère les inscriptions, et en L7 (K1) le jour J, les attestations et les
    # lettres d'invitation.
    "OC_FINANCE": {R, SR, PGR, RGR, RGM, PRW, FIR, CKS} | L8_TEAM | {BGR, BGW, SPR},
    "OC_SECRETARIAT": {R, SR, PGR, RGR, RGM, CKS, CKM, CEM, LEM} | L8_TEAM | {LGR, SVM},
    # K1 (plan L7) : le CO « bénévoles » gère les pointages et les bénévoles (eux seuls) ; les
    # « relations extérieures » instruisent les lettres d'invitation.
    "OC_VOLUNTEERS": {R, SR, PGR, RGR, CKS, CKM, MR, MM} | L8_TEAM | {VLP},
    "OC_EXTERNAL_RELATIONS": {R, SR, PGR, RGR, CKS, LEM} | L8_TEAM | {SPR, SPW},
    "SC_MEMBER": {RW},  # F10 : pas les soumissions ; H19 : ses affectations seulement
    "VOLUNTEER": {CKS, SHO},  # K1 (plan L7) : pointer ; N2 (plan L8) : son planning
    "SIGNATORY": {SGM},  # K18 (plan L7) : sa signature, rien d'autre
    "AUTHOR": set(),
}
# Profils qui ne sont pas un rôle seul : (rôle, fonction au CO).
PROFILE_ROLES = {
    "OC_MEMBER": (Role.OC_MEMBER, "logistics"),
    "OC_COMMUNICATION": (Role.OC_MEMBER, "communication"),
    "OC_PROGRAM": (Role.OC_MEMBER, "program"),
    "OC_FINANCE": (Role.OC_MEMBER, "finance"),
    "OC_SECRETARIAT": (Role.OC_MEMBER, "secretariat"),
    "OC_VOLUNTEERS": (Role.OC_MEMBER, "volunteers"),
    "OC_EXTERNAL_RELATIONS": (Role.OC_MEMBER, "external_relations"),
}
# Profils sans rôle actif dans l'édition visée : 404 (D5).
NON_MEMBERS = ("no_role", "other_edition_chair", "revoked_chair", "invited")
PROFILES = ("anonymous", *NON_MEMBERS, *SPEC)


@dataclass(frozen=True)
class Case:
    route: str
    method: str
    capability: str
    success: int
    path: str  # gabarit : {e} édition, {track}, {type}, {date}, {role}, {invitation}, {section}…
    body: dict | Callable[[dict], dict] | None = None  # fonction : corps calculé des ids
    recent_auth: bool = False
    format: str = "json"


CASES = [
    Case("manage-edition", "GET", R, 200, "/v1/manage/editions/{e}"),
    Case("manage-edition", "PATCH", W, 200, "/v1/manage/editions/{e}", {"venue": "Palais"}),
    Case(
        "manage-edition-status",
        "POST",
        PUB,
        200,
        "/v1/manage/editions/{e}/status",
        {"status": "published"},
        recent_auth=True,
    ),
    Case("manage-confidentiality", "GET", R, 200, "/v1/manage/editions/{e}/confidentiality"),
    Case(
        "manage-confidentiality",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/confidentiality",
        # Réglage non gelé : la soumission en recevabilité du monde gèle double_blind (RG-19).
        {"max_reviews_per_reviewer": 12},
        recent_auth=True,
    ),
    # Plan L6 (L6.1) : paramètres des inscriptions et mentions de facturation (J1).
    Case(
        "manage-registration-settings",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/settings",
    ),
    Case(
        "manage-registration-settings",
        "PATCH",
        PRW,
        200,
        "/v1/manage/editions/{e}/registrations/settings",
        {"online_deadline_hours": 48},
    ),
    # Plan L6 (L6.2) : catalogue des inscriptions (J2 à J4), lu par registrations.read, écrit
    # par pricing.write.
    Case(
        "manage-registration-categories",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/categories",
    ),
    Case(
        "manage-registration-categories",
        "POST",
        PRW,
        201,
        "/v1/manage/editions/{e}/registrations/categories",
        {"code": "matrice", "label_fr": "Matrice"},
    ),
    Case(
        "manage-registration-category",
        "PATCH",
        PRW,
        200,
        "/v1/manage/editions/{e}/registrations/categories/{reg_category}",
        {"label_fr": "Étudiant"},
    ),
    Case(
        "manage-registration-category",
        "DELETE",
        PRW,
        204,
        "/v1/manage/editions/{e}/registrations/categories/{reg_free_category}",
    ),
    Case(
        "manage-registration-category-fees",
        "PUT",
        PRW,
        200,
        "/v1/manage/editions/{e}/registrations/categories/{reg_category}/fees",
        {"fees": [{"period": "early", "zone": "local", "amount": "25000"}]},
    ),
    Case(
        "manage-registration-options",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/options",
    ),
    Case(
        "manage-registration-options",
        "POST",
        PRW,
        201,
        "/v1/manage/editions/{e}/registrations/options",
        {"code": "visite", "label_fr": "Visite"},
    ),
    Case(
        "manage-registration-option",
        "PATCH",
        PRW,
        200,
        "/v1/manage/editions/{e}/registrations/options/{reg_option}",
        {"quota": 50},
    ),
    Case(
        "manage-registration-option",
        "DELETE",
        PRW,
        204,
        "/v1/manage/editions/{e}/registrations/options/{reg_option}",
    ),
    Case(
        "manage-registration-promo-codes",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/promo-codes",
    ),
    Case(
        "manage-registration-promo-codes",
        "POST",
        PRW,
        201,
        "/v1/manage/editions/{e}/registrations/promo-codes",
        {"code": "MATRICE", "kind": "percent", "value": "10"},
    ),
    Case(
        "manage-registration-promo-code",
        "PATCH",
        PRW,
        200,
        "/v1/manage/editions/{e}/registrations/promo-codes/{reg_promo}",
        {"is_active": False},
    ),
    Case(
        "manage-registration-promo-code",
        "DELETE",
        PRW,
        204,
        "/v1/manage/editions/{e}/registrations/promo-codes/{reg_promo}",
    ),
    # Plan L6 (L6.3) : inscriptions (lecture registrations.read, actions registrations.manage),
    # paiements manuels, remboursements et factures en attente avec réauthentification (J1).
    Case("manage-registrations", "GET", RGR, 200, "/v1/manage/editions/{e}/registrations"),
    Case(
        "manage-registrations",
        "POST",
        RGM,
        201,
        "/v1/manage/editions/{e}/registrations",
        lambda ids: {"email": ids["reg_newcomer"], "category": "etudiant", "method": "onsite"},
    ),
    Case(
        "manage-registration",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_pending}",
    ),
    Case(
        "manage-registration-cancel",
        "POST",
        RGM,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_pending}/cancel",
        {"reason": "Matrice"},
    ),
    Case(
        "manage-registration-waive",
        "POST",
        RGM,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_pending}/waive",
        {"reason": "Matrice"},
    ),
    Case(
        "manage-registration-proof",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_pending}/proof",
    ),
    Case(
        "manage-registration-payments",
        "POST",
        RGM,
        201,
        "/v1/manage/editions/{e}/registrations/{reg_pending}/payments",
        lambda ids: {"method": "transfer", "amount": "2000", "received_on": ids["today"]},
        recent_auth=True,
    ),
    Case(
        "manage-registration-refunds",
        "POST",
        RGM,
        201,
        "/v1/manage/editions/{e}/registrations/{reg_cancelled}/refunds",
        lambda ids: {"amount": "2000", "method": "Virement", "refunded_on": ids["today"]},
        recent_auth=True,
    ),
    Case(
        "manage-registration-proforma",
        "POST",
        RGM,
        201,
        "/v1/manage/editions/{e}/registrations/{reg_pending}/proforma",
    ),
    Case(
        "manage-registration-document",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_paid}/documents/{reg_invoice}",
    ),
    Case("manage-billing-documents", "GET", FIR, 200, "/v1/manage/editions/{e}/billing/documents"),
    # Plan L6 (L6.5) : suivi financier et exports journalisés (réauthentification, J1).
    Case(
        "manage-registrations-export",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/export",
        recent_auth=True,
    ),
    Case("manage-billing-payments", "GET", FIR, 200, "/v1/manage/editions/{e}/billing/payments"),
    Case(
        "manage-billing-payments-export",
        "GET",
        FIR,
        200,
        "/v1/manage/editions/{e}/billing/payments/export",
        recent_auth=True,
    ),
    Case(
        "manage-billing-documents-export",
        "GET",
        FIR,
        200,
        "/v1/manage/editions/{e}/billing/documents/export",
        recent_auth=True,
    ),
    Case("manage-billing-dashboard", "GET", FIR, 200, "/v1/manage/editions/{e}/billing/dashboard"),
    Case(
        "manage-billing-issue-pending",
        "POST",
        RGM,
        200,
        "/v1/manage/editions/{e}/billing/documents/issue-pending",
        recent_auth=True,
    ),
    Case("manage-billing-profile", "GET", FIR, 200, "/v1/manage/editions/{e}/billing/profile"),
    Case(
        "manage-billing-profile",
        "PATCH",
        PRW,
        200,
        "/v1/manage/editions/{e}/billing/profile",
        {"legal_name": "Association matrice"},
        recent_auth=True,
    ),
    Case("manage-program-settings", "GET", PGR, 200, "/v1/manage/editions/{e}/program/settings"),
    Case(
        "manage-program-settings",
        "PATCH",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/settings",
        {"session_buffer_minutes": 5},
    ),
    # Plan L5 (L5.3) : brouillon du programme, lu par les comités, écrit par le CO
    # « programme » et l'administrateur (I1).
    Case("manage-program", "GET", PGR, 200, "/v1/manage/editions/{e}/program"),
    Case(
        "manage-program-rooms",
        "POST",
        PGW,
        201,
        "/v1/manage/editions/{e}/program/rooms",
        {"name": "Salle matrice"},
    ),
    Case(
        "manage-program-room",
        "PATCH",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/rooms/{room}",
        {"capacity": 50},
    ),
    Case(
        "manage-program-room",
        "DELETE",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/rooms/{free_room}",
    ),
    Case(
        "manage-program-sessions",
        "POST",
        PGW,
        201,
        "/v1/manage/editions/{e}/program/sessions",
        {
            "kind": "parallel",
            "title_fr": "Nouvelle",
            "starts_local": "2027-06-02T09:00",
            "ends_local": "2027-06-02T10:00",
        },
    ),
    Case(
        "manage-program-session",
        "PATCH",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/sessions/{program_session}",
        {"title_fr": "Renommée"},
    ),
    Case(
        "manage-program-session",
        "DELETE",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/sessions/{program_session}",
    ),
    Case(
        "manage-program-slots",
        "POST",
        PGW,
        201,
        "/v1/manage/editions/{e}/program/sessions/{program_session}/slots",
        lambda ids: {"submission": ids["confirmed_submission"]},
    ),
    Case(
        "manage-program-slot",
        "PATCH",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/slots/{slot}",
        {"duration_min": 25},
    ),
    Case("manage-program-slot", "DELETE", PGW, 200, "/v1/manage/editions/{e}/program/slots/{slot}"),
    Case(
        "manage-program-roles",
        "POST",
        PGW,
        201,
        "/v1/manage/editions/{e}/program/sessions/{program_session}/roles",
        lambda ids: {"user": ids["program_member"], "role": "discussant"},
    ),
    Case(
        "manage-program-role",
        "DELETE",
        PGW,
        200,
        "/v1/manage/editions/{e}/program/session-roles/{session_role}",
    ),
    Case("manage-program-people", "GET", PGW, 200, "/v1/manage/editions/{e}/program/people"),
    # I6 : publication par le Chair, réauthentification récente ; historique (I13).
    Case(
        "manage-program-publish",
        "POST",
        PGP,
        200,
        "/v1/manage/editions/{e}/program/publish",
        recent_auth=True,
    ),
    Case(
        "manage-program-publications",
        "GET",
        PGR,
        200,
        "/v1/manage/editions/{e}/program/publications",
    ),
    Case("manage-tracks-list", "GET", R, 200, "/v1/manage/editions/{e}/tracks"),
    Case(
        "manage-tracks-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/tracks",
        {"code": "nouvelle", "name_fr": "Nouvelle"},
    ),
    Case("manage-tracks-detail", "GET", R, 200, "/v1/manage/editions/{e}/tracks/{track}"),
    Case(
        "manage-tracks-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/tracks/{track}",
        {"name_en": "Updated"},
    ),
    Case("manage-tracks-detail", "DELETE", W, 204, "/v1/manage/editions/{e}/tracks/{track}"),
    Case("manage-submission-types-list", "GET", R, 200, "/v1/manage/editions/{e}/submission-types"),
    Case(
        "manage-submission-types-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/submission-types",
        {"code": "poster", "label_fr": "Poster"},
    ),
    Case(
        "manage-submission-types-detail",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/submission-types/{type}",
    ),
    Case(
        "manage-submission-types-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/submission-types/{type}",
        {"label_en": "Talk"},
    ),
    Case(
        "manage-submission-types-detail",
        "DELETE",
        W,
        204,
        "/v1/manage/editions/{e}/submission-types/{type}",
    ),
    Case("manage-key-dates-list", "GET", R, 200, "/v1/manage/editions/{e}/key-dates"),
    Case(
        "manage-key-dates-list",
        "POST",
        W,
        201,
        "/v1/manage/editions/{e}/key-dates",
        {"code": "atelier", "at_local": "2027-06-02T09:00", "label_fr": "Atelier"},
    ),
    Case("manage-key-dates-detail", "GET", R, 200, "/v1/manage/editions/{e}/key-dates/{date}"),
    Case(
        "manage-key-dates-detail",
        "PATCH",
        W,
        200,
        "/v1/manage/editions/{e}/key-dates/{date}",
        {"is_public": False},
    ),
    Case("manage-key-dates-detail", "DELETE", W, 204, "/v1/manage/editions/{e}/key-dates/{date}"),
    Case("manage-roles", "GET", MR, 200, "/v1/manage/editions/{e}/roles"),
    Case(
        "manage-role-revoke",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/roles/{role}/revoke",
        {"reason": "Fin de mandat"},
        recent_auth=True,
    ),
    Case("manage-invitations", "GET", MR, 200, "/v1/manage/editions/{e}/invitations"),
    Case(
        "manage-invitations",
        "POST",
        MM,
        201,
        "/v1/manage/editions/{e}/invitations",
        # Rôle que le profil gère : comité scientifique, bénévoles pour le CO « bénévoles ».
        lambda ids: {"emails": ["nouveau.membre@example.org"], "role": ids["invite_role"]},
    ),
    Case(
        "manage-invitation-resend",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/invitations/{invitation}/resend",
    ),
    Case(
        "manage-invitation-cancel",
        "POST",
        MM,
        200,
        "/v1/manage/editions/{e}/invitations/{invitation}/cancel",
    ),
    Case("manage-audit", "GET", AR, 200, "/v1/manage/editions/{e}/audit"),
    # --- Portail (lot L2, plan L2 §4) : lecture edition.read, écriture portal.write ----------
    Case("manage-portal-sections-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/sections"),
    Case(
        "manage-portal-sections-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/sections",
        {"code": "bienvenue", "section_type": "rich_text", "body_fr": "<p>Bienvenue</p>"},
    ),
    Case(
        "manage-portal-sections-detail",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/portal/sections/{section}",
    ),
    Case(
        "manage-portal-sections-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/sections/{section}",
        {"title_en": "Welcome"},
    ),
    Case(
        "manage-portal-sections-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/sections/{section}",
    ),
    Case(
        "manage-portal-sections-preview",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/sections/preview",
        {"body_fr": "<p>Aperçu</p>"},
    ),
    Case("manage-portal-pages-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/pages"),
    Case(
        "manage-portal-pages-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/pages",
        {"slug": "acces", "title_fr": "Accès"},
    ),
    Case(
        "manage-portal-pages-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/pages/{page}"
    ),
    Case(
        "manage-portal-pages-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}",
        {"title_en": "Practical information"},
    ),
    Case(
        "manage-portal-pages-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/pages/{page}",
    ),
    Case(
        "manage-portal-pages-attach",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/attach",
        lambda ids: {"section": ids["section"]},
    ),
    Case(
        "manage-portal-pages-detach",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/detach",
        lambda ids: {"section": ids["placed_section"]},
    ),
    Case(
        "manage-portal-pages-reorder",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/pages/{page}/reorder",
        lambda ids: {"sections": [ids["placed_section"]]},
    ),
    Case("manage-portal-menu-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/menu"),
    Case(
        "manage-portal-menu-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/menu",
        {"location": "footer", "label_fr": "Contact", "url": "mailto:contact@example.org"},
    ),
    Case("manage-portal-menu-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/menu/{menu}"),
    Case(
        "manage-portal-menu-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/menu/{menu}",
        {"label_en": "Call"},
    ),
    Case(
        "manage-portal-menu-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/menu/{menu}",
    ),
    Case(
        "manage-portal-menu-reorder",
        "POST",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/menu/reorder",
        lambda ids: {"location": "header", "items": list(reversed(ids["header_menu"]))},
    ),
    Case("manage-portal-status", "GET", R, 200, "/v1/manage/editions/{e}/portal/status"),
    # --- Fichiers publics (L2.4) ---------------------------------------------------------------
    Case("manage-portal-files-list", "GET", R, 200, "/v1/manage/editions/{e}/portal/files"),
    Case(
        "manage-portal-files-list",
        "POST",
        PW,
        201,
        "/v1/manage/editions/{e}/portal/files",
        lambda ids: {
            "file": SimpleUploadedFile("appel.pdf", PDF, "application/pdf"),
            "kind": "document",
        },
        format="multipart",
    ),
    Case(
        "manage-portal-files-detail", "GET", R, 200, "/v1/manage/editions/{e}/portal/files/{file}"
    ),
    Case(
        "manage-portal-files-detail",
        "PATCH",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/files/{file}",
        {"published": True},
    ),
    Case(
        "manage-portal-files-detail",
        "DELETE",
        PW,
        204,
        "/v1/manage/editions/{e}/portal/files/{file}",
    ),
    Case(
        "manage-portal-files-content",
        "GET",
        R,
        200,
        "/v1/manage/editions/{e}/portal/files/{file}/content",
    ),
    # --- Soumissions (lot L3, plan L3 §4) ---------------------------------------------------
    Case("manage-submissions-list", "GET", SR, 200, "/v1/manage/editions/{e}/submissions"),
    Case("manage-submissions-stats", "GET", SR, 200, "/v1/manage/editions/{e}/submissions/stats"),
    Case("manage-submissions-export", "GET", SX, 200, "/v1/manage/editions/{e}/submissions/export"),
    Case(
        "manage-submissions-detail",
        "GET",
        SR,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}",
    ),
    Case(
        "manage-submissions-file-content",
        "GET",
        SR,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}/files/{submission_file}/content",
    ),
    Case(
        "manage-submissions-extensions",
        "POST",
        SE,
        201,
        "/v1/manage/editions/{e}/submissions/{submission}/extensions",
        {"until_local": "2099-04-02T23:59", "reason": "Panne de courant"},
    ),
    Case(
        "manage-submissions-extension-revoke",
        "POST",
        SE,
        200,
        "/v1/manage/editions/{e}/submissions/{submission}/extensions/{extension}/revoke",
    ),
    # --- Évaluation (lot L4, plan L4 §4) : grilles -----------------------------------------
    Case("manage-grids-list", "GET", R, 200, "/v1/manage/editions/{e}/grids"),
    Case("manage-grids-list", "POST", GW, 201, "/v1/manage/editions/{e}/grids", {"name": "Poster"}),
    Case("manage-grids-detail", "GET", R, 200, "/v1/manage/editions/{e}/grids/{grid}"),
    Case(
        "manage-grids-detail",
        "PATCH",
        GW,
        200,
        "/v1/manage/editions/{e}/grids/{grid}",
        {"name": "Grille révisée"},
    ),
    Case("manage-grids-detail", "DELETE", GW, 204, "/v1/manage/editions/{e}/grids/{grid}"),
    Case(
        "manage-grids-duplicate", "POST", GW, 201, "/v1/manage/editions/{e}/grids/{grid}/duplicate"
    ),
    # --- Recevabilité, affectations, conflits (L4.2) ------------------------------------------
    Case(
        "manage-review-submissions-list",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions",
    ),
    Case(
        "manage-review-submissions-detail",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}",
    ),
    Case(
        "manage-review-submissions-candidates",
        "GET",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}/candidates",
    ),
    Case(
        "manage-review-submissions-screening",
        "POST",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{review_submission}/screening",
        {"decision": "reject", "reason": "Hors du champ de la conférence"},
    ),
    Case(
        "manage-assignments-list",
        "POST",
        RM,
        201,
        "/v1/manage/editions/{e}/assignments",
        lambda ids: {"submission": ids["review_submission"], "reviewer": ids["reviewer"]},
    ),
    Case(
        "manage-assignments-detail",
        "PATCH",
        RM,
        200,
        "/v1/manage/editions/{e}/assignments/{assignment}",
        {"due_local": "2099-05-01T23:59"},
    ),
    Case(
        "manage-assignments-cancel",
        "POST",
        RM,
        200,
        "/v1/manage/editions/{e}/assignments/{assignment}/cancel",
        {"reason": "Remplacement"},
    ),
    Case(
        "manage-conflicts-list",
        "POST",
        RM,
        201,
        "/v1/manage/editions/{e}/conflicts",
        lambda ids: {
            "submission": ids["review_submission"],
            "reviewer": ids["reviewer"],
            "reason": "Collaboration récente",
        },
    ),
    # --- Évaluations, discussion, suivi (président, L4.3) -------------------------------------
    Case(
        "manage-review-submissions-reviews",
        "GET",
        RA,
        200,
        "/v1/manage/editions/{e}/review-submissions/{discussed_submission}/reviews",
    ),
    Case(
        "manage-review-submissions-discussion-open",
        "POST",
        RM,
        200,
        "/v1/manage/editions/{e}/review-submissions/{open_submission}/discussion/open",
    ),
    Case(
        "manage-review-submissions-discussion-messages",
        "POST",
        RM,
        201,
        "/v1/manage/editions/{e}/review-submissions/{discussed_submission}/discussion/messages",
        {"body": "Pouvez-vous préciser la méthode ?"},
    ),
    Case("manage-review-progress", "GET", RM, 200, "/v1/manage/editions/{e}/review-progress"),
    # --- Décisions, publication, classement, export (L4.4) ------------------------------------
    Case(
        "manage-review-submissions-decision",
        "PUT",
        DD,
        200,
        "/v1/manage/editions/{e}/review-submissions/{discussed_submission}/decision",
        {"outcome": "accepted"},
    ),
    Case(
        "manage-review-submissions-decision",
        "DELETE",
        DD,
        200,
        "/v1/manage/editions/{e}/review-submissions/{discussed_submission}/decision",
    ),
    Case(
        "manage-review-submissions-promote",
        "POST",
        DP,
        200,
        "/v1/manage/editions/{e}/review-submissions/{waitlisted_submission}/promote",
    ),
    Case(
        "manage-decisions-batch",
        "POST",
        DD,
        200,
        "/v1/manage/editions/{e}/decisions/batch",
        lambda ids: {"items": [{"submission": ids["discussed_submission"], "outcome": "rejected"}]},
    ),
    Case(
        "manage-decisions-publish",
        "POST",
        DP,
        200,
        "/v1/manage/editions/{e}/decisions/publish",
        recent_auth=True,
    ),
    Case("manage-ranking", "GET", RA, 200, "/v1/manage/editions/{e}/ranking?threshold=50"),
    Case(
        "manage-reviews-export",
        "GET",
        RA,
        200,
        "/v1/manage/editions/{e}/reviews-export",
        recent_auth=True,
    ),
    # --- Espace relecteur (L4.3) : ses affectations seulement ({my_*} : celle du profil) -----
    Case(
        "reviewer-assignments-list", "GET", RW, 200, "/v1/manage/editions/{e}/reviews/assignments"
    ),
    Case(
        "reviewer-assignments-detail",
        "GET",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}",
    ),
    Case(
        "reviewer-assignments-file",
        "GET",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}/file",
    ),
    Case(
        "reviewer-assignments-authors",
        "GET",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}/authors",
    ),
    Case(
        "reviewer-assignments-decline",
        "POST",
        RW,
        204,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}/decline",
        {"reason": "Indisponible"},
    ),
    Case(
        "reviewer-review",
        "PUT",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}/review",
        {"scores": {"originalite": "4"}},
    ),
    Case(
        "reviewer-review-submit",
        "POST",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_assignment}/review/submit",
        {
            "scores": {code: "4" for code in ("originalite", "methode", "pertinence")}
            | {"redaction": "3", "impact": "3"},
            "recommendation": "accept",
            "confidence": 4,
            "comment_to_authors": "Travail solide.",
        },
    ),
    Case(
        "reviewer-discussion",
        "GET",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/assignments/{my_discussed}/discussion",
    ),
    Case(
        "reviewer-discussion",
        "POST",
        RW,
        201,
        "/v1/manage/editions/{e}/reviews/assignments/{my_discussed}/discussion",
        {"body": "Je maintiens ma note."},
    ),
    Case("reviewer-expertise", "GET", RW, 200, "/v1/manage/editions/{e}/reviews/expertise"),
    Case(
        "reviewer-expertise",
        "PUT",
        RW,
        200,
        "/v1/manage/editions/{e}/reviews/expertise",
        lambda ids: {"tracks": [ids["track_code"]]},
    ),
    # --- Signature du signataire (plan L7, K18) : la sienne, lue et écrite par lui seul ------
    Case("manage-signature", "GET", SGM, 200, "/v1/manage/editions/{e}/signature"),
    Case(
        "manage-signature",
        "PATCH",
        SGM,
        200,
        "/v1/manage/editions/{e}/signature",
        {"title_en": "Conference chair"},
        recent_auth=True,
    ),
    Case("manage-signature-image", "GET", SGM, 200, "/v1/manage/editions/{e}/signature/image"),
    Case(
        "manage-signature-image",
        "PUT",
        SGM,
        200,
        "/v1/manage/editions/{e}/signature/image",
        lambda ids: {"file": SimpleUploadedFile("signature.png", _signature_png(), "image/png")},
        recent_auth=True,
        format="multipart",
    ),
    # --- Pointage à l'accueil et badges (plan L7, K2 à K5) -----------------------------------
    Case("manage-checkin-summary", "GET", CKS, 200, "/v1/manage/editions/{e}/checkin/summary"),
    Case("manage-checkin-bundle", "GET", CKS, 200, "/v1/manage/editions/{e}/checkin/bundle"),
    Case(
        "manage-checkin-scan",
        "POST",
        CKS,
        200,
        "/v1/manage/editions/{e}/checkin/scan",
        lambda ids: {"token": ids["reg_token"]},
    ),
    Case(
        "manage-checkin-sync",
        "POST",
        CKS,
        200,
        "/v1/manage/editions/{e}/checkin/sync",
        lambda ids: {
            "items": [
                {
                    "idempotency_key": "matrice-0001",
                    "token": ids["reg_token"],
                    "scanned_at": "2027-06-01T08:00:00Z",
                }
            ]
        },
    ),
    Case(
        "manage-checkin-manual",
        "POST",
        CKM,
        200,
        "/v1/manage/editions/{e}/checkin/manual",
        lambda ids: {"reference": ids["reg_reference"]},
    ),
    Case("manage-checkin", "GET", CKM, 200, "/v1/manage/editions/{e}/checkin"),
    Case(
        "manage-checkin-cancel",
        "POST",
        CKM,
        200,
        "/v1/manage/editions/{e}/checkin/{checkin}/cancel",
        {"reason": "Erreur d'accueil"},
    ),
    Case(
        "manage-checkin-export",
        "GET",
        CKM,
        200,
        "/v1/manage/editions/{e}/checkin/export",
        recent_auth=True,
    ),
    Case(
        "manage-badges-batches",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/badges/batches",
    ),
    # Paramètre lu dans les objets d'inscription : leur création (paresseuse) précède l'appel.
    Case(
        "manage-badges",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/badges?category={reg_category_code}",
    ),
    Case(
        "manage-badge",
        "GET",
        RGR,
        200,
        "/v1/manage/editions/{e}/registrations/{reg_paid}/badge",
    ),
    Case(
        "manage-badge-regenerate",
        "POST",
        CKM,
        204,
        "/v1/manage/editions/{e}/registrations/{reg_paid}/regenerate-token",
        {"reason": "Badge perdu"},
    ),
    # --- Émargement et « présentée » (plan L7, K7, K8) : capacité, ou présidence de séance
    # (testée à part, le président de la session du jour J n'étant pas un profil de la matrice).
    # Paramètre ignoré par la vue : il fait créer le programme publié avant l'appel.
    Case(
        "manage-day-sessions",
        "GET",
        CKS,
        200,
        "/v1/manage/editions/{e}/day/sessions?session={day_session}",
    ),
    Case(
        "manage-day-attendance",
        "GET",
        CKM,
        200,
        "/v1/manage/editions/{e}/day/sessions/{day_session}/attendance",
    ),
    Case(
        "manage-day-attendance-scan",
        "POST",
        CKS,
        200,
        "/v1/manage/editions/{e}/day/sessions/{day_session}/attendance/scan",
        lambda ids: {"token": ids["day_token"]},
    ),
    Case(
        "manage-day-attendance-export",
        "GET",
        CKM,
        200,
        "/v1/manage/editions/{e}/day/sessions/{day_session}/attendance/export",
        recent_auth=True,
    ),
    Case(
        "manage-day-presented",
        "POST",
        PGW,
        200,
        "/v1/manage/editions/{e}/day/sessions/{day_session}/slots/{day_scheduled_slot}/presented",
    ),
    Case(
        "manage-day-unpresented",
        "POST",
        PGW,
        200,
        "/v1/manage/editions/{e}/day/sessions/{day_session}/slots/{day_presented_slot}/unpresented",
        {"reason": "Erreur de saisie"},
    ),
    # --- Attestations (plan L7, K9 à K11, K18, K19) : certificates.manage ; objets créés au
    # premier cas qui les vise ({certificate}, ou un paramètre ignoré par la vue).
    Case(
        "manage-certificate-settings",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings",
    ),
    Case(
        "manage-certificate-settings",
        "PATCH",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings",
        {"layout": "signature_left"},
        recent_auth=True,
    ),
    Case(
        "manage-certificate-header",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings/header?c={certificate}",
    ),
    Case(
        "manage-certificate-header",
        "PUT",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings/header",
        lambda ids: {"file": SimpleUploadedFile("logo.png", _signature_png(), "image/png")},
        recent_auth=True,
        format="multipart",
    ),
    Case(
        "manage-certificate-header",
        "DELETE",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings/header",
        recent_auth=True,
    ),
    Case(
        "manage-certificate-signing-key",
        "PUT",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings/signing-key",
        lambda ids: {
            "file": SimpleUploadedFile("cle.p12", _signing_key()),
            "password": "secret-de-test",
        },
        recent_auth=True,
        format="multipart",
    ),
    Case(
        "manage-certificate-signing-key",
        "DELETE",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/settings/signing-key",
        recent_auth=True,
    ),
    Case(
        "manage-certificate-templates",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/templates",
    ),
    Case(
        "manage-certificate-template",
        "PATCH",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/templates/participation",
        {"footer_fr": "Université de la matrice"},
        recent_auth=True,
    ),
    Case(
        "manage-certificate-preview",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/templates/participation/preview",
    ),
    Case(
        "manage-certificate-signatories",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/signatories",
    ),
    Case(
        "manage-certificates-overview",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/overview",
    ),
    Case(
        "manage-certificates-issue",
        "POST",
        CEM,
        202,
        "/v1/manage/editions/{e}/certificates/issue?c={certificate}",
        {"nature": "participation"},
        recent_auth=True,
    ),
    Case("manage-certificates", "GET", CEM, 200, "/v1/manage/editions/{e}/certificates"),
    Case(
        "manage-certificate-pdf",
        "GET",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/{certificate}/pdf",
    ),
    Case(
        "manage-certificate-revoke",
        "POST",
        CEM,
        200,
        "/v1/manage/editions/{e}/certificates/{certificate}/revoke",
        {"reason": "Erreur"},
        recent_auth=True,
    ),
    # --- Lettres d'invitation (plan L7, K12) : letters.manage --------------------------------
    Case(
        "manage-letters",
        "GET",
        LEM,
        200,
        "/v1/manage/editions/{e}/invitation-letters?l={letter}",
    ),
    Case("manage-letter", "GET", LEM, 200, "/v1/manage/editions/{e}/invitation-letters/{letter}"),
    Case(
        "manage-letter-issue",
        "POST",
        LEM,
        200,
        "/v1/manage/editions/{e}/invitation-letters/{letter}/issue",
        recent_auth=True,
    ),
    Case(
        "manage-letter-refuse",
        "POST",
        LEM,
        200,
        "/v1/manage/editions/{e}/invitation-letters/{letter}/refuse",
        {"reason": "Dates incohérentes"},
    ),
    Case(
        "manage-letter-revoke",
        "POST",
        LEM,
        200,
        "/v1/manage/editions/{e}/invitation-letters/{issued_letter}/revoke",
        {"reason": "Erreur"},
        recent_auth=True,
    ),
    Case(
        "manage-letter-pdf",
        "GET",
        LEM,
        200,
        "/v1/manage/editions/{e}/invitation-letters/{issued_letter}/pdf",
    ),
    # --- Comptoir (plan L7, K13) : registrations.manage --------------------------------------
    Case(
        "manage-registrations-counter",
        "POST",
        RGM,
        201,
        "/v1/manage/editions/{e}/registrations/counter",
        lambda ids: {
            "email": "comptoir@example.org",
            "first_name": "Kojo",
            "last_name": "Mensah",
            "country": "FR",
            "category": ids["reg_category_code"],
        },
    ),
    # --- Organisation (plan L8, N3, N4) : tâches du CO, budget ---------------------------------
    Case("manage-tasks", "GET", TKR, 200, "/v1/manage/editions/{e}/tasks"),
    Case("manage-tasks", "POST", TKW, 201, "/v1/manage/editions/{e}/tasks", {"title": "Salle"}),
    Case("manage-tasks-members", "GET", TKR, 200, "/v1/manage/editions/{e}/tasks/members"),
    Case("manage-task", "GET", TKR, 200, "/v1/manage/editions/{e}/tasks/{task}"),
    Case(
        "manage-task",
        "PATCH",
        TKW,
        200,
        "/v1/manage/editions/{e}/tasks/{task}",
        {"status": "doing"},
    ),
    Case("manage-task-archive", "POST", TKW, 200, "/v1/manage/editions/{e}/tasks/{task}/archive"),
    Case("manage-task-restore", "POST", TKW, 200, "/v1/manage/editions/{e}/tasks/{task}/restore"),
    Case(
        "manage-task-comments",
        "POST",
        TKW,
        201,
        "/v1/manage/editions/{e}/tasks/{task}/comments",
        {"body": "Devis reçu."},
    ),
    Case(
        "manage-task-attachments",
        "POST",
        TKW,
        201,
        "/v1/manage/editions/{e}/tasks/{task}/attachments",
        lambda ids: {"file": SimpleUploadedFile("devis.pdf", PDF, "application/pdf")},
        format="multipart",
    ),
    Case(
        "manage-task-attachment",
        "GET",
        TKR,
        200,
        "/v1/manage/editions/{e}/tasks/{task}/attachments/{task_attachment}",
    ),
    Case(
        "manage-task-attachment",
        "DELETE",
        TKW,
        200,
        "/v1/manage/editions/{e}/tasks/{task}/attachments/{task_attachment}",
    ),
    Case("manage-budget", "GET", BGR, 200, "/v1/manage/editions/{e}/budget"),
    Case(
        "manage-budget-export",
        "GET",
        BGR,
        200,
        "/v1/manage/editions/{e}/budget/export?file_format=xlsx",
        recent_auth=True,
    ),
    Case(
        "manage-budget-lines",
        "POST",
        BGW,
        201,
        "/v1/manage/editions/{e}/budget/lines",
        {"kind": "expense", "category": "venue", "label": "Location", "planned": "500000"},
    ),
    Case(
        "manage-budget-line",
        "PATCH",
        BGW,
        200,
        "/v1/manage/editions/{e}/budget/lines/{budget_line}",
        {"planned": "600000"},
    ),
    Case(
        "manage-budget-line",
        "DELETE",
        BGW,
        200,
        "/v1/manage/editions/{e}/budget/lines/{budget_line}",
    ),
    Case(
        "manage-budget-line-proof",
        "GET",
        BGR,
        200,
        "/v1/manage/editions/{e}/budget/lines/{budget_line}/proof",
    ),
    Case(
        "manage-budget-line-proof",
        "PUT",
        BGW,
        200,
        "/v1/manage/editions/{e}/budget/lines/{budget_line}/proof",
        lambda ids: {"file": SimpleUploadedFile("facture.pdf", PDF, "application/pdf")},
        format="multipart",
    ),
    Case(
        "manage-budget-line-proof",
        "DELETE",
        BGW,
        200,
        "/v1/manage/editions/{e}/budget/lines/{budget_line}/proof",
    ),
    # --- Partenaires (plan L8, N5) -------------------------------------------------------------
    Case("manage-sponsors", "GET", SPR, 200, "/v1/manage/editions/{e}/sponsors"),
    Case(
        "manage-sponsors", "POST", SPW, 201, "/v1/manage/editions/{e}/sponsors", {"name": "Orange"}
    ),
    Case(
        "manage-sponsors-export",
        "GET",
        SPR,
        200,
        "/v1/manage/editions/{e}/sponsors/export?file_format=csv",
        recent_auth=True,
    ),
    Case("manage-sponsor", "GET", SPR, 200, "/v1/manage/editions/{e}/sponsors/{sponsor}"),
    Case(
        "manage-sponsor",
        "PATCH",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsors/{sponsor}",
        {"status": "agreed"},
    ),
    Case("manage-sponsor", "DELETE", SPW, 204, "/v1/manage/editions/{e}/sponsors/{sponsor}"),
    Case(
        "manage-sponsor-logo",
        "PUT",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsors/{sponsor}/logo",
        lambda ids: {"file": SimpleUploadedFile("logo.png", _signature_png(), "image/png")},
        format="multipart",
    ),
    Case(
        "manage-sponsor-logo", "DELETE", SPW, 200, "/v1/manage/editions/{e}/sponsors/{sponsor}/logo"
    ),
    Case(
        "manage-sponsor-benefits",
        "POST",
        SPW,
        201,
        "/v1/manage/editions/{e}/sponsors/{sponsor}/benefits",
        {"label": "Logo sur les badges"},
    ),
    Case(
        "manage-sponsor-benefit",
        "PATCH",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsors/{sponsor}/benefits/{benefit}",
        lambda ids: {"delivered_on": ids["today"]},
    ),
    Case(
        "manage-sponsor-benefit",
        "DELETE",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsors/{sponsor}/benefits/{benefit}",
    ),
    Case("manage-sponsor-levels", "GET", SPR, 200, "/v1/manage/editions/{e}/sponsor-levels"),
    Case(
        "manage-sponsor-levels",
        "POST",
        SPW,
        201,
        "/v1/manage/editions/{e}/sponsor-levels",
        {"name_fr": "Or", "logo_size": "large"},
    ),
    Case(
        "manage-sponsor-level",
        "PATCH",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsor-levels/{sponsor_level}",
        {"position": 2},
    ),
    Case(
        "manage-sponsor-level",
        "DELETE",
        SPW,
        200,
        "/v1/manage/editions/{e}/sponsor-levels/{free_sponsor_level}",
    ),
    # --- Logistique (plan L8, N6 à N9) ----------------------------------------------------------
    Case("manage-visits", "GET", LGR, 200, "/v1/manage/editions/{e}/logistics/visits"),
    Case("manage-visit", "GET", LGR, 200, "/v1/manage/editions/{e}/logistics/visits/{speaker}"),
    Case(
        "manage-visit",
        "PATCH",
        LGW,
        200,
        "/v1/manage/editions/{e}/logistics/visits/{speaker}",
        {"hotel": "Hôtel Ivoire", "status": "booked"},
    ),
    Case("manage-dietary", "GET", LGR, 200, "/v1/manage/editions/{e}/logistics/dietary"),
    Case(
        "manage-dietary-export",
        "GET",
        LGR,
        200,
        "/v1/manage/editions/{e}/logistics/dietary/export",
        recent_auth=True,
    ),
    Case("manage-meals", "GET", LGR, 200, "/v1/manage/editions/{e}/logistics/meals"),
    Case(
        "manage-meals",
        "POST",
        LGW,
        201,
        "/v1/manage/editions/{e}/logistics/meals",
        lambda ids: {"day": ids["meal_day"], "kind": "lunch"},
    ),
    Case("manage-meals-export", "GET", LGR, 200, "/v1/manage/editions/{e}/logistics/meals/export"),
    Case(
        "manage-meal",
        "PATCH",
        LGW,
        200,
        "/v1/manage/editions/{e}/logistics/meals/{meal}",
        {"margin_percent": 10},
    ),
    Case("manage-meal", "DELETE", LGW, 200, "/v1/manage/editions/{e}/logistics/meals/{meal}"),
    Case("manage-shifts", "GET", VLP, 200, "/v1/manage/editions/{e}/logistics/shifts"),
    Case(
        "manage-shifts",
        "POST",
        VLP,
        201,
        "/v1/manage/editions/{e}/logistics/shifts",
        {
            "title_fr": "Vestiaire",
            "starts_local": "2027-06-02T14:00",
            "ends_local": "2027-06-02T18:00",
        },
    ),
    Case(
        "manage-shift",
        "PATCH",
        VLP,
        200,
        "/v1/manage/editions/{e}/logistics/shifts/{shift}",
        {"needed": 3},
    ),
    Case("manage-shift", "DELETE", VLP, 200, "/v1/manage/editions/{e}/logistics/shifts/{shift}"),
    Case(
        "manage-shift-assignments",
        "POST",
        VLP,
        201,
        "/v1/manage/editions/{e}/logistics/shifts/{shift}/assignments",
        lambda ids: {"volunteer": ids["volunteer"]},
    ),
    Case(
        "manage-shift-assignment",
        "DELETE",
        VLP,
        200,
        "/v1/manage/editions/{e}/logistics/shifts/{shift}/assignments/{volunteer}",
    ),
    Case("manage-my-shifts", "GET", SHO, 200, "/v1/manage/editions/{e}/me/shifts"),
    Case(
        "manage-my-shifts-calendar", "GET", SHO, 200, "/v1/manage/editions/{e}/me/shifts/calendar"
    ),
    # --- Annonces et envois groupés (plan L8, N10 et N11) -------------------------------------
    Case("manage-segments", "GET", CMS, 200, "/v1/manage/editions/{e}/segments"),
    Case("manage-announcements", "GET", CMS, 200, "/v1/manage/editions/{e}/announcements"),
    Case(
        "manage-announcements",
        "POST",
        CMS,
        201,
        "/v1/manage/editions/{e}/announcements",
        {"title_fr": "Programme en ligne", "on_news": True, "body_fr": "<p>Voir.</p>"},
    ),
    Case(
        "manage-announcement",
        "GET",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{announcement}",
    ),
    Case(
        "manage-announcement",
        "PATCH",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{announcement}",
        {"title_fr": "Salle changée"},
    ),
    Case(
        "manage-announcement",
        "DELETE",
        CMS,
        204,
        "/v1/manage/editions/{e}/announcements/{announcement}",
    ),
    Case(
        "manage-announcement-preview",
        "GET",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{announcement}/preview",
    ),
    Case(
        "manage-announcement-test",
        "POST",
        CMS,
        202,
        "/v1/manage/editions/{e}/announcements/{announcement}/test",
    ),
    Case(
        "manage-announcement-publish",
        "POST",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{announcement}/publish",
        recent_auth=True,
    ),
    Case(
        "manage-announcement-withdraw",
        "POST",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{published_announcement}/withdraw",
    ),
    Case(
        "manage-announcement-cancel",
        "POST",
        CMS,
        200,
        "/v1/manage/editions/{e}/announcements/{sending_announcement}/cancel",
    ),
    Case("manage-portal-poster", "GET", R, 200, "/v1/manage/editions/{e}/portal/poster"),
    Case(
        "manage-portal-poster",
        "PUT",
        PW,
        200,
        "/v1/manage/editions/{e}/portal/poster",
        lambda ids: {"file": ids["image"]},
    ),
]

PDF = b"%PDF-1.7\n%%EOF\n"


def expected_status(case: Case, profile: str) -> int:
    if profile == "anonymous":
        return 401
    if profile in NON_MEMBERS:
        return 404
    return case.success if case.capability in SPEC[profile] else 403


MATRIX = [
    pytest.param(
        case,
        profile,
        expected_status(case, profile),
        id=f"{case.route}-{case.method}-{profile}-{expected_status(case, profile)}",
    )
    for case in CASES
    for profile in PROFILES
]


@pytest.fixture(autouse=True)
def _cheap_pdf(monkeypatch):
    """La matrice teste les droits, pas les PDF (testés dans ``apps.payments``) : un PDF
    minimal évite le coût du sous-ensemble de police à chaque pièce émise."""
    monkeypatch.setattr("apps.payments.pdf.render", lambda data: b"%PDF-1.7\n%%EOF\n")


@pytest.fixture
def world():
    """Édition complète (publiable) avec un membre de chaque rôle et les objets visés. Sans
    double aveugle : la route relecteur des auteurs y répond (elle rend 404 en double aveugle,
    ce que testent les tests de fuite RG-04)."""
    edition = EditionFactory(double_blind=False)
    other = EditionFactory()
    track = TrackFactory(edition=edition)
    submission_type = SubmissionTypeFactory(edition=edition)
    KeyDateFactory(edition=edition, code="call_open", at=dt.datetime(2027, 1, 10, tzinfo=dt.UTC))
    key_date = KeyDateFactory(
        edition=edition, code="call_close", at=dt.datetime(2027, 3, 31, tzinfo=dt.UTC)
    )
    users = {}
    for profile in SPEC:
        role, oc_function = PROFILE_ROLES.get(profile, (profile, None))
        users[profile] = make_member(edition, role, oc_function=oc_function)
    users["no_role"] = VerifiedUserFactory()
    users["other_edition_chair"] = make_member(other, Role.CHAIR)
    users["revoked_chair"] = make_member(edition, Role.CHAIR, status=UserRoleStatus.REVOKED)
    invited = VerifiedUserFactory()
    users["invited"] = invited
    now = timezone.now()
    RoleInvitation.objects.create(
        edition=edition,
        email=invited.email,
        role=Role.CHAIR,
        token_hash=token_hash("jeton-invite-chair"),
        pending_key=pending_key(edition.pk, invited.email, Role.CHAIR, ""),
        expires_at=now + dt.timedelta(days=14),
        locale="fr",
        last_sent_at=now,
    )
    # Cibles des actions sur les membres et les invitations : comité scientifique, que
    # tous les détenteurs de members.manage peuvent gérer (SC_CHAIR compris).
    target_member = make_member(edition, Role.SC_MEMBER)
    target_role = UserRole.objects.get(user=target_member, edition=edition)
    invitation = RoleInvitation.objects.create(
        edition=edition,
        email="relecteur.invite@example.org",
        role=Role.SC_MEMBER,
        token_hash=token_hash("jeton-relecteur"),
        pending_key=pending_key(edition.pk, "relecteur.invite@example.org", Role.SC_MEMBER, ""),
        expires_at=now + dt.timedelta(days=14),
        locale="fr",
        last_sent_at=now,
    )
    # Portail : section libre (posable, supprimable), section posée sur une page personnalisée.
    section = Section.objects.create(edition=edition, code="libre", section_type="rich_text")
    placed = Section.objects.create(edition=edition, code="posee", section_type="rich_text")
    page = Page.objects.create(edition=edition, slug="infos", title_fr="Infos")
    PageSection.objects.create(page=page, section=placed, position=0)
    header_menu = list(
        MenuItem.objects.filter(edition=edition, location="header")
        .order_by("position")
        .values_list("pk", flat=True)
    )
    document = public_files.store(
        data=PDF, name="modele.pdf", kind=PublicFileKind.DOCUMENT, edition=edition
    )
    image = public_files.store(
        data=_png(), name="affiche.png", kind=PublicFileKind.IMAGE, edition=edition
    )
    submission, submission_file, extension = _submission_with_extension(edition)
    from apps.core.actor import Actor
    from apps.reviews.services.grids import create_grid

    grid = create_grid(edition, name="Grille", actor=Actor.command("cli:matrice"))
    review_submission, reviewer, assignment = _review_objects(edition)
    reviewing = _reviewer_objects(edition, users)
    # Mentions de facturation complètes (plan L6, J8) : les pièces peuvent s'émettre.
    from apps.payments.services.billing import billing_profile

    profile = billing_profile(edition)
    profile.legal_name, profile.address = "Association matrice", "Abidjan"
    profile.save()
    reviewing["per_profile"]["OC_VOLUNTEERS"] = _member_objects(edition, users, now)
    ids = LazyIds(
        {
            **reviewing,
            **_program_objects(edition, users),
            "track_code": track.code,
            "grid": grid.pk,
            "review_submission": review_submission.pk,
            "reviewer": reviewer.pk,
            "assignment": assignment.pk,
            "submission": submission.pk,
            "submission_file": submission_file.pk,
            "extension": extension.pk,
            "file": document.pk,
            "image": image.pk,
            "section": section.pk,
            "placed_section": placed.pk,
            "page": page.pk,
            "menu": header_menu[0],
            "header_menu": header_menu,
            "e": edition.pk,
            "track": track.pk,
            "type": submission_type.pk,
            "date": key_date.pk,
            "role": target_role.pk,
            "invitation": invitation.pk,
            "invite_role": "SC_MEMBER",
        },
        # Inscriptions, paiements et pièces (plan L6) : créés au premier cas qui les vise,
        # leurs PDF coûtant cher à produire pour chacun des cas. Programme publié du jour J
        # (plan L7) : à part, pour que les cas de publication du programme restent valables.
        loaders=(
            lambda: _organisation_objects(edition, users),
            lambda: _registration_objects(edition),
            lambda: _day_objects(edition),
            lambda: _certificate_objects(edition, users),
            lambda: _letter_objects(edition, users),
        ),
    )
    return edition, users, ids


def _organisation_objects(edition, users) -> dict:
    """Plan L8 (N3, N4) : une tâche avec sa pièce jointe ; une ligne de budget justifiée."""
    from apps.logistics.models import BudgetLine, Task, TaskAttachment
    from apps.logistics.services.budget import PROOFS
    from apps.logistics.services.tasks import ATTACHMENTS

    task = Task.objects.create(edition=edition, title="Réserver le traiteur")
    storage, digest = ATTACHMENTS.write(PDF)
    attachment = TaskAttachment.objects.create(
        task=task,
        storage_name=storage,
        name="devis.pdf",
        kind="pdf",
        size=len(PDF),
        sha256=digest,
        uploaded_by=users["ADMIN"],
    )
    proof, _digest = PROOFS.write(PDF)
    line = BudgetLine.objects.create(
        edition=edition,
        kind="expense",
        category="catering",
        label="Traiteur",
        planned=1000,
        proof_storage_name=proof,
        proof_name="facture.pdf",
        proof_kind="pdf",
        proof_size=len(PDF),
    )
    from apps.sponsors.models import Sponsor, SponsorBenefit, SponsorLevel

    level = SponsorLevel.objects.create(edition=edition, name_fr="Platine", position=0)
    free = SponsorLevel.objects.create(edition=edition, name_fr="Bronze", position=1)
    sponsor = Sponsor.objects.create(edition=edition, name="Banque Atlantique", level=level)
    benefit = SponsorBenefit.objects.create(sponsor=sponsor, label="Stand")
    from apps.logistics.models import Meal, ShiftAssignment, VolunteerShift

    speaker = make_member(edition, Role.SPEAKER)
    day = edition.start_date or timezone.localdate()
    meal = Meal.objects.create(edition=edition, day=day, kind="lunch")
    start = dt.datetime(2027, 6, 2, 8, tzinfo=dt.UTC)
    shift = VolunteerShift.objects.create(
        edition=edition, title_fr="Accueil", starts_at=start, ends_at=start + dt.timedelta(hours=4)
    )
    ShiftAssignment.objects.create(shift=shift, volunteer=users["VOLUNTEER"])
    from apps.communications import announcements
    from apps.core.actor import Actor

    command = Actor.command("cli:matrice")
    capabilities = {"communications.send"}
    found = {}
    for key, fields in (
        ("announcement", {"on_bell": True}),
        ("published_announcement", {"on_news": True}),
        ("sending_announcement", {"on_bell": True}),
    ):
        found[key] = announcements.create_announcement(
            edition,
            {
                "title_fr": "Changement de salle",
                "body_fr": "<p>Salle A.</p>",
                "segment": "volunteers",
                **fields,
            },
            capabilities=capabilities,
            actor=command,
        )
    for key in ("published_announcement", "sending_announcement"):
        announcements.publish(found[key], capabilities=capabilities, actor=command)
    return {
        **{key: announcement.pk for key, announcement in found.items()},
        "speaker": speaker.pk,
        "meal_day": day.isoformat(),
        "meal": meal.pk,
        "shift": shift.pk,
        "volunteer": users["VOLUNTEER"].pk,
        "task": task.pk,
        "task_attachment": attachment.pk,
        "budget_line": line.pk,
        "sponsor": sponsor.pk,
        "benefit": benefit.pk,
        "sponsor_level": level.pk,
        "free_sponsor_level": free.pk,
    }


@functools.cache
def _signing_key() -> bytes:
    """PKCS#12 jetable (créé une fois par session de test : la clé RSA coûte)."""
    from apps.events.tests.certificate_helpers import pkcs12_file

    data, _certificate = pkcs12_file()
    return data


def _letter_objects(edition, users) -> dict:
    """Plan L7 (K12) : signataire désigné pour les lettres ; une demande en cours et une
    lettre émise."""
    from apps.core.actor import Actor
    from apps.events.services import certificates, letters
    from apps.events.services.signatures import signature_of
    from apps.events.tests.letter_helpers import PASSPORT
    from apps.registrations.models import RegistrationStatus
    from apps.registrations.tests.factories import make_registration

    command = Actor.command("cli:matrice")
    signature = signature_of(edition, users["SIGNATORY"])
    certificates.update_template(edition, "letter", {"signatory": signature.pk}, actor=command)
    found = {}
    for key in ("letter", "issued_letter"):
        registration = make_registration(
            edition, VerifiedUserFactory(), status=RegistrationStatus.PENDING
        )
        found[key] = letters.request_letter(registration, PASSPORT, actor=command)
    letters.issue_letter(found["issued_letter"], actor=command)
    return {key: letter.pk for key, letter in found.items()}


def _certificate_objects(edition, users) -> dict:
    """Plan L7 (K9 à K11, K19) : en-tête déposé, signataire désigné, une personne pointée et
    son attestation émise."""
    from apps.core.actor import Actor
    from apps.events.models import Certificate
    from apps.events.services import certificates
    from apps.events.services.signatures import signature_of
    from apps.events.tests.certificate_helpers import present

    command = Actor.command("cli:matrice")
    certificates.upload_header(edition, data=_signature_png(), actor=command)
    signature = signature_of(edition, users["SIGNATORY"])
    certificates.update_template(
        edition, "participation", {"signatory": signature.pk}, actor=command
    )
    present(edition)
    certificates.issue_batch(edition, "participation")
    # Deux attestations au moins (la personne pointée par les objets d'inscription aussi).
    return {"certificate": Certificate.objects.filter(edition=edition).order_by("id")[0].pk}


def _day_objects(edition) -> dict:
    """Plan L7 (K7, K8) : session publiée (instantané posé directement, sans toucher à l'état
    du programme), présidée par une personne hors des profils de la matrice, avec une
    communication programmée et une présentée ; une inscription confirmée à pointer."""
    from apps.program.models import ProgramPublication, Room, Session, SessionRole, Slot
    from apps.program.services.publication import build_snapshot
    from apps.registrations.models import RegistrationStatus
    from apps.registrations.tests.factories import make_registration
    from apps.submissions.models import Submission, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    room = Room.objects.create(edition=edition, name="Salle du jour J")
    start = dt.datetime(2027, 6, 2, 9, tzinfo=dt.UTC)
    day = Session.objects.create(
        edition=edition,
        kind="parallel",
        title_fr="Session du jour J",
        room=room,
        starts_at=start,
        ends_at=start + dt.timedelta(hours=2),
    )
    SessionRole.objects.create(
        session=day, user=make_member(edition, Role.SESSION_CHAIR), role="chair"
    )
    slots = {}
    for position, (status, number, last) in enumerate(
        ((SubmissionStatus.SCHEDULED, 6, "Boateng"), (SubmissionStatus.PRESENTED, 7, "Ofori"))
    ):
        paper = complete_submission(edition, author_user(first="Yaw", last=last))
        Submission.objects.filter(pk=paper.pk).update(
            status=status, reference=f"{edition.code}-{number:04d}"
        )
        begins = start + dt.timedelta(minutes=30 * position)
        slots[status] = Slot.objects.create(
            session=day,
            position=position,
            duration_min=20,
            submission_id=paper.pk,
            starts_at=begins,
            ends_at=begins + dt.timedelta(minutes=20),
        )
    ProgramPublication.objects.create(
        edition=edition,
        version=1000,
        revision=0,
        published_at=timezone.now(),
        snapshot=build_snapshot(edition, [day]),
    )
    registration = make_registration(
        edition, VerifiedUserFactory(), status=RegistrationStatus.CONFIRMED
    )
    return {
        "day_session": day.pk,
        "day_scheduled_slot": slots[SubmissionStatus.SCHEDULED].pk,
        "day_presented_slot": slots[SubmissionStatus.PRESENTED].pk,
        "day_token": registration.qr_token,
    }


def _program_objects(edition, users) -> dict:
    """Plan L5 : salle utilisée et salle libre, session avec un créneau libre et un rôle de
    séance, communication confirmée à placer, personne de l'édition pour un rôle."""
    from apps.program.models import Room, Session, SessionRole, Slot
    from apps.submissions.models import Submission, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    room = Room.objects.create(edition=edition, name="Amphi matrice")
    free_room = Room.objects.create(edition=edition, name="Salle libre")
    start = dt.datetime(2027, 6, 1, 9, tzinfo=dt.UTC)
    session = Session.objects.create(
        edition=edition,
        kind="parallel",
        title_fr="Session matrice",
        room=room,
        starts_at=start,
        ends_at=start + dt.timedelta(hours=2),
    )
    slot = Slot.objects.create(
        session=session,
        position=0,
        duration_min=20,
        title_fr="Ouverture",
        starts_at=start,
        ends_at=start + dt.timedelta(minutes=20),
    )
    role = SessionRole.objects.create(session=session, user=users["SC_CHAIR"], role="chair")
    paper = complete_submission(edition, author_user(first="Kwame", last="Asante"))
    Submission.objects.filter(pk=paper.pk).update(
        status=SubmissionStatus.CONFIRMED, reference=f"{edition.code}-0005"
    )
    return {
        "room": room.pk,
        "free_room": free_room.pk,
        "program_session": session.pk,
        "slot": slot.pk,
        "session_role": role.pk,
        "confirmed_submission": paper.pk,
        "program_member": users["SC_MEMBER"].pk,
    }


def _registration_objects(edition) -> dict:
    """Plan L6 : catalogue (catégorie à tarif, option et code promo supprimables), dates
    d'inscription ouvertes, mentions complètes ; une inscription en attente (avec
    justificatif), une payée (facture), une payée puis annulée ; un compte sans inscription."""
    from decimal import Decimal

    from apps.accounts.models import Profile
    from apps.conferences.models import KeyDate
    from apps.core.actor import Actor
    from apps.payments.models import BillingDocument
    from apps.payments.services import documents, manual
    from apps.registrations.models import Fee, PromoCode, RegistrationCategory, RegistrationOption
    from apps.registrations.services import orders

    now = timezone.now()
    KeyDate.objects.create(edition=edition, code="registration_open", at=now - dt.timedelta(1))
    KeyDate.objects.create(edition=edition, code="early_bird_end", at=now + dt.timedelta(10))
    category = RegistrationCategory.objects.create(
        edition=edition, code="etudiant", label_fr="Étudiant", requires_proof=True
    )
    Fee.objects.create(category=category, period="early", zone="local", amount=Decimal("1000"))
    for period in ("early", "onsite"):
        Fee.objects.create(
            category=category, period=period, zone="international", amount=Decimal("2000")
        )
    free = RegistrationCategory.objects.create(edition=edition, code="libre", label_fr="Libre")
    option = RegistrationOption.objects.create(edition=edition, code="diner", label_fr="Dîner")
    promo = PromoCode.objects.create(
        edition=edition, code="ETU", kind="percent", value=Decimal("10")
    )
    documents.prepare_series(edition)
    command = Actor.command("cli:matrice")

    def person():
        user = VerifiedUserFactory()
        Profile.objects.create(user=user, first_name="Ama", last_name="Mensah", country="FR")
        return user

    def order():
        # Saisie par le CO : l'édition de la matrice n'est pas publiée.
        return orders.place_order(
            edition,
            person(),
            category="etudiant",
            method="transfer",
            actor=command,
            by_committee=True,
        )

    def pay(registration):
        manual.record_manual_payment(
            registration,
            method="transfer",
            amount=registration.total,
            reference="",
            received_on=timezone.localdate(),
            actor=command,
        )

    pending = order()
    orders.upload_proof(pending, data=PDF, name="carte.pdf", actor=command)
    paid = order()
    pay(paid)
    cancelled = order()
    pay(cancelled)
    orders.cancel_by_committee(cancelled, reason="Matrice", percent=100, actor=command)
    invoice = BillingDocument.objects.get(registration=paid, kind="invoice")
    # Plan L7 : jeton du badge de l'inscription payée, et un pointage à annuler (celui d'une
    # autre inscription confirmée, pour que le badge payé reste à pointer).
    from apps.events.services import checkin as checkin_services
    from apps.registrations.models import Registration

    token = Registration.objects.get(pk=paid.pk).qr_token
    checked = order()
    pay(checked)
    checkin = checkin_services.check_in(
        edition, token=Registration.objects.get(pk=checked.pk).qr_token, actor=command
    ).checkin
    return {
        "reg_category": category.pk,
        "reg_free_category": free.pk,
        "reg_option": option.pk,
        "reg_promo": promo.pk,
        "reg_pending": pending.pk,
        "reg_paid": paid.pk,
        "reg_cancelled": cancelled.pk,
        "reg_invoice": invoice.pk,
        "reg_token": token,
        "reg_category_code": category.code,
        "reg_reference": paid.reference,
        "checkin": checkin.pk,
        "reg_newcomer": person().email,
        "today": timezone.localdate().isoformat(),
    }


def _submission_with_extension(edition):
    """Brouillon avec un PDF et une dérogation, pour les routes de gestion. Un brouillon, et
    non une soumission : celle-ci gèlerait ``double_blind`` (RG-19) et la case
    « confidentialité » testerait la règle au lieu du droit."""
    from apps.submissions import storage
    from apps.submissions.models import SubmissionExtension, SubmissionFile
    from apps.submissions.tests.factories import author_user, complete_submission

    # Thématique et type propres : ceux de la matrice restent supprimables (sinon 409 in_use).
    submission = complete_submission(edition, author_user())
    name, digest = storage.write(PDF)
    submission_file = SubmissionFile.objects.create(
        submission=submission,
        kind="main",
        version=1,
        storage_name=name,
        original_name="article.pdf",
        size=len(PDF),
        sha256=digest,
        pages=1,
        is_current=True,
        uploaded_by=submission.submitter,
    )
    extension = SubmissionExtension.objects.create(
        submission=submission,
        until=timezone.now() + dt.timedelta(days=2),
        reason="Accordée",
        granted_at=timezone.now(),
    )
    return submission, submission_file, extension


def _review_objects(edition):
    """Soumission en recevabilité (statut posé directement : la clôture de l'appel n'est pas
    passée), un relecteur libre et une affectation active d'un autre relecteur."""
    from apps.reviews.models import ReviewAssignment
    from apps.submissions.models import Submission, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    submission = complete_submission(edition, author_user(first="Kofi", last="Mensah"))
    Submission.objects.filter(pk=submission.pk).update(
        status=SubmissionStatus.SCREENING, reference=f"{edition.code}-0001"
    )
    reviewer = make_member(edition, Role.SC_MEMBER)
    assigned = make_member(edition, Role.SC_MEMBER)
    assignment = ReviewAssignment.objects.create(
        submission=submission,
        reviewer=assigned,
        assigned_at=timezone.now(),
        pseudonym_rank=1,
        active_key=f"{submission.pk}:{assigned.pk}",
    )
    return submission, reviewer, assignment


def _reviewer_objects(edition, users):
    """Pour chaque profil qui évalue (SC_MEMBER, SC_CHAIR) : une affectation sur une soumission
    en évaluation (avec PDF), une autre sur une soumission évaluée, son évaluation envoyée et
    la discussion ouverte. Grille propre au type de ces soumissions : la grille du monde reste
    modifiable (cases des grilles)."""
    from decimal import Decimal

    from apps.core.actor import Actor
    from apps.reviews.models import Decision, Discussion, Review, ReviewAssignment, ReviewStatus
    from apps.reviews.services.grids import create_grid
    from apps.submissions import storage
    from apps.submissions.models import Submission, SubmissionFile, SubmissionStatus
    from apps.submissions.tests.factories import author_user, complete_submission

    open_submission = complete_submission(edition, author_user(first="Ama", last="Owusu"))
    Submission.objects.filter(pk=open_submission.pk).update(
        status=SubmissionStatus.UNDER_REVIEW, reference=f"{edition.code}-0002"
    )
    discussed = complete_submission(
        edition,
        author_user(first="Yao", last="Kouassi"),
        submission_type=open_submission.submission_type,
    )
    Submission.objects.filter(pk=discussed.pk).update(
        status=SubmissionStatus.REVIEWED, reference=f"{edition.code}-0003"
    )
    grid = create_grid(
        edition,
        name="Grille du type",
        submission_type=open_submission.submission_type,
        actor=Actor.command("cli:matrice"),
    )
    name, digest = storage.write(PDF)
    SubmissionFile.objects.create(
        submission=open_submission,
        kind="main",
        version=1,
        storage_name=name,
        original_name="article.pdf",
        size=len(PDF),
        sha256=digest,
        pages=1,
        is_current=True,
        uploaded_by=open_submission.submitter,
    )
    Discussion.objects.create(submission=discussed, opened_at=timezone.now())
    waitlisted = complete_submission(edition, author_user(first="Efua", last="Mensah"))
    Submission.objects.filter(pk=waitlisted.pk).update(
        status=SubmissionStatus.WAITLIST, reference=f"{edition.code}-0004"
    )
    Decision.objects.create(
        submission=waitlisted,
        outcome="waitlist",
        decided_by=users["CHAIR"],
        decided_at=timezone.now(),
        published_at=timezone.now(),
    )
    per_profile = {}
    now = timezone.now()
    for rank, profile in enumerate(("SC_MEMBER", "SC_CHAIR"), start=1):
        user = users[profile]
        mine = ReviewAssignment.objects.create(
            submission=open_submission,
            reviewer=user,
            assigned_at=now,
            pseudonym_rank=rank,
            active_key=f"{open_submission.pk}:{user.pk}",
        )
        done = ReviewAssignment.objects.create(
            submission=discussed,
            reviewer=user,
            assigned_at=now,
            pseudonym_rank=rank,
            active_key=f"{discussed.pk}:{user.pk}",
        )
        Review.objects.create(
            assignment=done,
            grid=grid,
            status=ReviewStatus.SUBMITTED,
            recommendation="accept",
            confidence=3,
            comment_to_authors="Bien.",
            weighted_score=Decimal("70.00"),
            submitted_at=now,
            version=1,
        )
        per_profile[profile] = {"my_assignment": mine.pk, "my_discussed": done.pk}
    return {
        "open_submission": open_submission.pk,
        "discussed_submission": discussed.pk,
        "waitlisted_submission": waitlisted.pk,
        "per_profile": per_profile,
        "my_assignment": per_profile["SC_MEMBER"]["my_assignment"],
        "my_discussed": per_profile["SC_MEMBER"]["my_discussed"],
    }


def _png(size=(20, 10)) -> bytes:
    import io

    from PIL import Image

    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, "PNG")
    return output.getvalue()


def _signature_png() -> bytes:
    return _png((240, 80))


def _member_objects(edition, users, now) -> dict:
    """Plan L7 (K1, K18) : un bénévole et une invitation de bénévole, cibles du CO
    « bénévoles », qui ne voit qu'eux ; la signature complète du signataire."""
    from apps.core.actor import Actor
    from apps.events.services import signatures

    volunteer = make_member(edition, Role.VOLUNTEER)
    invitation = RoleInvitation.objects.create(
        edition=edition,
        email="benevole.invite@example.org",
        role=Role.VOLUNTEER,
        token_hash=token_hash("jeton-benevole"),
        pending_key=pending_key(edition.pk, "benevole.invite@example.org", Role.VOLUNTEER, ""),
        expires_at=now + dt.timedelta(days=14),
        locale="fr",
        last_sent_at=now,
    )
    signatory = users["SIGNATORY"]
    command = Actor.command("cli:matrice")
    signatures.update_details(
        edition,
        signatory,
        display_name="Pr Awa Diallo",
        title_fr="Présidente du comité d'organisation",
        title_en="",
        actor=command,
    )
    signatures.upload_image(edition, signatory, data=_signature_png(), actor=command)
    return {
        "role": UserRole.objects.get(user=volunteer, edition=edition).pk,
        "invitation": invitation.pk,
        "invite_role": "VOLUNTEER",
    }


def call(client: APIClient, case: Case, ids: dict):
    path = case.path.format_map(ids)
    method = getattr(client, case.method.lower())
    if case.body is None:
        return method(path)
    body = case.body(ids) if callable(case.body) else case.body
    return method(path, body, format=case.format)


@pytest.mark.parametrize(("case", "profile", "expected"), MATRIX)
def test_matrix(world, case, profile, expected):
    """Plan L1 §5.9 : anonyme 401, non-membre 404, membre sans capacité 403, sinon succès."""
    _edition, users, ids = world
    client = APIClient() if profile == "anonymous" else client_for(users[profile])
    response = call(client, case, for_profile(ids, profile))
    assert response.status_code == expected, response.content


class LazyIds(dict):
    """Identifiants du monde, dont une partie est créée à la première lecture d'une clé
    absente (``loaders``, dans l'ordre, chacun une fois) ; une vue par profil délègue à son
    parent les clés qu'elle n'a pas."""

    def __init__(self, data, *, loaders=(), parent=None):
        super().__init__(data)
        self._loaders = list(loaders)
        self._parent = parent

    def __missing__(self, key):
        if self._parent is not None:
            return self._parent[key]
        while self._loaders:
            self.update(self._loaders.pop(0)())
            if dict.__contains__(self, key):
                return self[key]
        raise KeyError(key)


def for_profile(ids: dict, profile: str) -> dict:
    """Identifiants propres au profil (affectations du relecteur : 404 pour un autre)."""
    return LazyIds(ids.get("per_profile", {}).get(profile, {}), parent=ids)


def holder(capability: str) -> str:
    """Premier profil de gestion qui détient ``capability`` (ordre de ``SPEC``)."""
    return next(profile for profile in SPEC if capability in SPEC[profile])


@pytest.mark.parametrize(
    "case", [case for case in CASES if case.recent_auth], ids=lambda c: f"{c.route}-{c.method}"
)
def test_matrix_stale_reauthentication(world, case):
    """D12 : sans réauthentification de moins de 5 min → 403 ``reauthentication_required``."""
    _edition, users, ids = world
    profile = holder(case.capability)
    response = call(client_for(users[profile], recent_auth=False), case, for_profile(ids, profile))
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"


def test_matrix_archived_edition_is_read_only(world):
    """§6.3 : une édition archivée est en lecture seule (409 ``edition_archived``)."""
    edition, users, ids = world
    # Objets paresseux (inscriptions, jour J, attestations) créés avant l'archivage.
    assert ids["reg_pending"] and ids["day_session"] and ids["certificate"] and ids["letter"]
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    clients = {}
    for case in CASES:
        profile = holder(case.capability)
        if profile not in clients:
            clients[profile] = client_for(users[profile])
        response = call(clients[profile], case, for_profile(ids, profile))
        if case.method == "GET":
            assert response.status_code == 200, case
        elif case.route != "manage-edition-status":
            assert response.status_code == 409, (case, response.content)
            assert response.json()["code"] == "edition_archived"


def test_manage_response_order_401_404_403_mfa():
    """D5, §4.4 : l'ordre des contrôles ne révèle pas l'existence d'une édition, et la 2FA
    n'est demandée qu'à un membre qui détient la capacité (401 → 404 → 403 → 403 mfa)."""
    edition = EditionFactory()
    author = make_member(edition, Role.AUTHOR)
    stranger = VerifiedUserFactory()
    path = f"/v1/manage/editions/{edition.pk}"
    assert APIClient().get(path).status_code == 401
    assert APIClient().get("/v1/manage/editions/999999").status_code == 401
    assert client_for(stranger).get(path).status_code == 404
    assert client_for(stranger).get("/v1/manage/editions/999999").status_code == 404
    response = client_for(author).get(path)
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"
    # Un non-membre sans 2FA reçoit toujours 404, jamais une demande de 2FA.
    assert client_for(stranger, mfa=False).get(path).status_code == 404
    chair = make_member(edition, Role.CHAIR)
    response = client_for(chair, mfa=False).get(path)
    assert (response.status_code, response.json()["code"]) == (403, "mfa_enrollment_required")


def test_object_of_another_edition_is_404(world):
    _edition, users, ids = world
    other_track = TrackFactory()
    path = f"/v1/manage/editions/{ids['e']}/tracks/{other_track.pk}"
    assert client_for(users["ADMIN"]).get(path).status_code == 404


# --- Liste des éditions (ManageEditionListView, §5.3, D3) -------------------------------


def test_edition_list_cases(world):
    edition, users, _ids = world
    assert APIClient().get("/v1/manage/editions").status_code == 401
    assert client_for(users["no_role"]).get("/v1/manage/editions").json() == []
    assert client_for(users["AUTHOR"]).get("/v1/manage/editions").json() == []
    body = client_for(users["CHAIR"]).get("/v1/manage/editions").json()
    assert [item["id"] for item in body] == [edition.pk]
    # Champs non sensibles seulement.
    assert set(body[0]) == {"id", "code", "title_fr", "title_en", "year", "status"}
    other = client_for(users["other_edition_chair"]).get("/v1/manage/editions").json()
    assert edition.pk not in [item["id"] for item in other]


# --- Filtrage par rôle (§5.4) -----------------------------------------------------------


def test_sc_chair_only_sees_scientific_committee(world):
    _edition, users, ids = world
    client = client_for(users["SC_CHAIR"])
    roles = {
        member["role"] for member in client.get(f"/v1/manage/editions/{ids['e']}/roles").json()
    }
    assert roles == {"SC_CHAIR", "SC_MEMBER"}
    invitations = client.get(f"/v1/manage/editions/{ids['e']}/invitations").json()["results"]
    assert {item["role"] for item in invitations} == {"SC_MEMBER"}


def test_member_email_visible_only_with_members_manage(world):
    _edition, users, ids = world
    members = client_for(users["SC_CHAIR"]).get(f"/v1/manage/editions/{ids['e']}/roles").json()
    assert all("email" in member for member in members)
    # Lecture seule des membres : aucun profil de L1 n'a members.read sans members.manage ;
    # le sérialiseur sans adresse reste le repli (échec fermé), testé directement.
    from apps.accounts.manage_serializers import MemberSerializer

    assert "email" not in MemberSerializer().fields


def test_sc_chair_cannot_invite_chair(world):
    _edition, users, ids = world
    response = client_for(users["SC_CHAIR"]).post(
        f"/v1/manage/editions/{ids['e']}/invitations",
        {"emails": ["x@example.org"], "role": "CHAIR"},
        format="json",
    )
    assert response.status_code == 403


def test_pending_invitation_gives_no_right(world):
    """D6 : un invité ne détient aucun droit, par construction."""
    _edition, users, ids = world
    assert RoleInvitation.objects.filter(status=InvitationStatus.PENDING).exists()
    response = client_for(users["invited"]).get(f"/v1/manage/editions/{ids['e']}")
    assert response.status_code == 404


# --- Complétude (§5.9) ----------------------------------------------------------------------


def _manage_routes():
    def walk(patterns, prefix=""):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns, prefix + str(pattern.pattern))
            elif isinstance(pattern, URLPattern):
                yield prefix + str(pattern.pattern), pattern

    for route, pattern in walk(get_resolver().url_patterns):
        if route.startswith("v1/manage/editions/<int:edition_id>"):
            actions = getattr(pattern.callback, "actions", {}) or {}
            for method in actions:
                if method not in ("head", "options"):
                    yield pattern.name, method.upper()


def test_every_manage_route_is_in_matrix():
    """Un endpoint ajouté sous v1/manage/editions/{id}/ ne peut pas échapper à la matrice."""
    covered = {(case.route, case.method) for case in CASES}
    missing = sorted(set(_manage_routes()) - covered)
    assert missing == []


def test_h2_reviewer_routes_require_two_factor_authentication(world):
    """H2 (plan L4) : la 2FA est imposée aux relecteurs (SC_MEMBER) sur leurs routes."""
    _edition, users, ids = world
    path = f"/v1/manage/editions/{ids['e']}/reviews/assignments"
    response = client_for(users["SC_MEMBER"], mfa=False).get(path)
    assert (response.status_code, response.json()["code"]) == (403, "mfa_enrollment_required")
    assert client_for(users["SC_MEMBER"]).get(path).status_code == 200


def test_profile_capabilities_match_spec(world):
    """Les capacités de chaque profil, lues par ``/v1/me``, sont celles de la spécification,
    y compris celles qui n'ont pas encore de route (plan L7 : pointage, attestations,
    lettres)."""
    edition, users, _ids = world
    for profile in SPEC:
        body = client_for(users[profile]).get("/v1/me").json()
        mine = next(item for item in body["editions"] if item["id"] == edition.pk)
        assert set(mine["capabilities"]) == SPEC[profile], profile


def test_k1_volunteers_committee_sees_and_manages_volunteers_only(world):
    """K1 (plan L7) : le CO « bénévoles » ne voit que les bénévoles parmi les membres et les
    invitations ; il invite des bénévoles, pas d'autres rôles ; un autre membre lui est
    introuvable."""
    _edition, users, ids = world
    client = client_for(users["OC_VOLUNTEERS"])
    base = f"/v1/manage/editions/{ids['e']}"
    roles = {member["role"] for member in client.get(f"{base}/roles").json()}
    assert roles == {"VOLUNTEER"}
    invitations = client.get(f"{base}/invitations").json()["results"]
    assert {item["role"] for item in invitations} == {"VOLUNTEER"}
    response = client.post(
        f"{base}/invitations", {"emails": ["x@example.org"], "role": "SC_MEMBER"}, format="json"
    )
    assert response.status_code == 403
    response = client.post(
        f"{base}/roles/{ids['role']}/revoke", {"reason": "Hors périmètre"}, format="json"
    )
    assert response.status_code == 404


@pytest.mark.parametrize(
    ("profile", "route"), [("VOLUNTEER", "checkin/summary"), ("SIGNATORY", "signature")]
)
def test_k1_k18_volunteer_and_signatory_require_two_factor_authentication(world, profile, route):
    """K1 et K18 (plan L7) : 2FA imposée aux bénévoles et aux signataires, annoncée par
    ``/v1/me`` et exigée sur leurs routes."""
    edition, users, ids = world
    client = client_for(users[profile], mfa=False)
    mine = next(
        item for item in client.get("/v1/me").json()["editions"] if item["id"] == edition.pk
    )
    assert mine["mfa_required"] is True
    response = client.get(f"/v1/manage/editions/{ids['e']}/{route}")
    assert (response.status_code, response.json()["code"]) == (403, "mfa_enrollment_required")
