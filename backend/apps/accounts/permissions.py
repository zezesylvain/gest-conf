"""Cadre de permissions par édition (plan L1 §5.1, §5.3, §4.4, §4.5 ; règles n° 2 et 5).

Ordre des contrôles, fixé et testé (D5) : anonyme → 401 ; non-membre → 404 ; membre sans
capacité → 403 ; rôle sensible sans 2FA → 403 ``mfa_*``. Pour le garantir,
l'édition et les droits sont chargés dans ``check_permissions``, que DRF appelle dans
``initial()``, après l'authentification et avant ``get_queryset()``.
"""

from __future__ import annotations

import time
from typing import Any

from allauth.account import app_settings as account_settings
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.viewsets import GenericViewSet

from apps.accounts.roles import Capability
from apps.accounts.services.access import EditionAccess, edition_access
from apps.core.errors import ErrorCode


class EditionScopedViewMixin:
    """Charge l'édition du chemin (``edition_id``) et l'``EditionAccess`` avant les permissions.

    L'édition n'est désignée **que** par le chemin (D5) : en-tête, paramètre ou corps
    sont ignorés. Anonyme : rien n'est chargé, ``IsAuthenticated`` répond 401.
    Non-membre : 404. Le queryset est toujours filtré par édition, puis par
    ``scope_queryset`` (filtrage par rôle, §5.4).
    """

    access: EditionAccess

    def check_permissions(self, request: Request) -> None:
        if request.user and request.user.is_authenticated:
            self.access = edition_access(request.user, self.kwargs["edition_id"])
        super().check_permissions(request)  # type: ignore[misc]

    @property
    def edition(self):
        return self.access.edition

    def get_queryset(self) -> QuerySet:
        queryset = super().get_queryset()  # type: ignore[misc]
        return self.scope_queryset(queryset.filter(edition=self.access.edition), self.access)

    def scope_queryset(self, queryset: QuerySet, access: EditionAccess) -> QuerySet:
        return queryset


class HasCapability(BasePermission):
    """Capacité exigée par la vue, par action (viewset) ou par méthode HTTP.

    ``view.required_capabilities = {"list": EDITION_READ, "partial_update": EDITION_WRITE}``.
    Échec fermé : une action ou une méthode non déclarée est refusée.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        access: EditionAccess | None = getattr(view, "access", None)
        if access is None:
            return False
        required: dict[str, Capability] = getattr(view, "required_capabilities", {})
        action = getattr(view, "action", None)
        capability = required.get(action) if action else None
        if capability is None:
            capability = required.get(request.method or "")
        return capability is not None and access.has(capability)


def session_has_mfa(request: Request) -> bool:
    """Vrai si la session a été validée par la 2FA (entrée ``mfa`` des enregistrements
    d'authentification d'allauth : connexion en deux étapes ou réauthentification 2FA).

    Seul point de lecture de cette structure interne, figée par un test de contrat (§4.5).
    """
    from allauth.account.authentication import get_authentication_records

    return any(record.get("method") == "mfa" for record in get_authentication_records(request))


class MfaVerified(BasePermission):
    """2FA imposée aux rôles de ``MFA_REQUIRED_ROLES`` dans l'édition du chemin (D3, §4.4).

    Vérifiée à chaque requête (*step-up*), après la capacité :
    1. 2FA non activée sur le compte → 403 ``mfa_enrollment_required`` ;
    2. session non validée par la 2FA → 403 ``mfa_required`` ;
    3. sinon, accès accordé. Un rôle non concerné (relecteur, auteur) passe toujours.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        from allauth.mfa.utils import is_mfa_enabled

        access: EditionAccess | None = getattr(view, "access", None)
        if access is None or not access.mfa_required:
            return True
        if not is_mfa_enabled(request.user):
            self.message = _("Activez la double authentification pour accéder à la gestion.")
            self.code = ErrorCode.MFA_ENROLLMENT_REQUIRED.value
            return False
        if not session_has_mfa(request):
            self.message = _("Confirmez votre identité avec votre code de double authentification.")
            self.code = ErrorCode.MFA_REQUIRED.value
            return False
        return True


def last_authentication_at(request: Request) -> float | None:
    """Horodatage (``time.time()``) de la dernière authentification de la session.

    Structure interne d'allauth (``account_authentication_methods``), figée par un test
    de contrat (§4.5) : jamais les fonctions ``internal`` d'allauth.
    """
    # Import différé : importé en premier, ce module d'allauth déclenche un import
    # circulaire interne (allauth 65.19.7, constaté).
    from allauth.account.authentication import get_authentication_records

    records = get_authentication_records(request)
    if not records:
        return None
    at = records[-1].get("at")
    return float(at) if isinstance(at, int | float) else None


def has_recent_authentication(request: Request) -> bool:
    at = last_authentication_at(request)
    return at is not None and time.time() - at <= account_settings.REAUTHENTICATION_TIMEOUT


class RecentAuthRequired(BasePermission):
    """Réauthentification de moins de 5 min (D12) : 403 ``reauthentication_required``.

    Angular ouvre alors la fenêtre de réauthentification et rejoue la requête une fois.
    """

    message = _("Confirmez votre mot de passe pour continuer.")
    code = ErrorCode.REAUTHENTICATION_REQUIRED.value

    def has_permission(self, request: Request, view: Any) -> bool:
        return has_recent_authentication(request)


class ManageViewSet(EditionScopedViewMixin, GenericViewSet):
    """Base de toutes les routes ``v1/manage/editions/{edition_id}/…`` (test de plateforme)."""

    permission_classes = (IsAuthenticated, HasCapability, MfaVerified)
    required_capabilities: dict[str, Capability] = {}
