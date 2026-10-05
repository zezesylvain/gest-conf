"""Permissions DRF transverses."""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.authentication import CsrfFailed, csrf_rejection_reason


class CsrfEnforced(BasePermission):
    """Impose le contrôle CSRF même à un visiteur anonyme (plan L1 §4.6, cas 3).

    DRF ne contrôle le CSRF que pour une session authentifiée, et ``csrf_protect``
    serait sans effet sur une vue DRF (déjà marquée ``csrf_exempt``). Cette
    permission appelle explicitement le même contrôle et lève ``CsrfFailed``
    (403 ``csrf_failed``) : à placer sur les POST publics (consultation ou refus
    d'une invitation par jeton, par exemple). Les méthodes sûres ne sont pas
    contrôlées, comme dans Django.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        if csrf_rejection_reason(request) is not None:
            raise CsrfFailed()
        return True
