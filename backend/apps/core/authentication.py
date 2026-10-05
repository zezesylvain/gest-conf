"""Authentification de l'API par la session Django (plan L1 §4.6, §9.1).

Deux écarts avec ``rest_framework.authentication.SessionAuthentication`` :

1. ``authenticate_header`` renvoie un schéma : DRF répond alors **401** (avec
   l'en-tête ``WWW-Authenticate``) à une requête sans session, au lieu de 403
   (``APIView.handle_exception`` ne garde le 401 que si cet en-tête existe).
2. ``enforce_csrf`` lève ``CsrfFailed`` (403 ``csrf_failed``) au lieu de
   ``PermissionDenied`` (403 ``permission_denied``) : les vues DRF étant exemptées
   du middleware CSRF, ``CSRF_FAILURE_VIEW`` n'est jamais appelée pour elles.

Ce module est importé par ``rest_framework.views`` (via ``DEFAULT_AUTHENTICATION_CLASSES``) :
il ne doit importer ni ``rest_framework.views`` ni ``apps.core.exceptions``, sous peine
d'import circulaire. ``CsrfFailed`` est donc défini ici.
"""

import logging

from django.utils.translation import gettext_lazy as _
from rest_framework import authentication, exceptions, status
from rest_framework.request import Request

from apps.core.errors import ErrorCode

# Même canal que les refus du middleware CSRF de Django.
security_logger = logging.getLogger("django.security.csrf")

# Schéma non standard : il ne déclenche pas la fenêtre d'authentification des
# navigateurs (contrairement à « Basic »), mais rend la réponse 401 conforme.
SESSION_AUTH_SCHEME = "Session"


class CsrfFailed(exceptions.APIException):
    """Échec du contrôle CSRF sous DRF (plan L1 §4.6), au lieu de ``permission_denied``.

    L'intercepteur Angular s'appuie sur ce code pour renouveler le jeton et
    rejouer la requête une seule fois.
    """

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _("Échec de la vérification CSRF : rechargez la page puis réessayez.")
    default_code = ErrorCode.CSRF_FAILED.value


def csrf_rejection_reason(request: Request) -> str | None:
    """Exécute le contrôle CSRF de Django sur ``request`` ; renvoie le motif de refus.

    Même mécanique que ``SessionAuthentication.enforce_csrf`` de DRF (``CSRFCheck``) ;
    ``None`` si la requête est acceptée (méthode sûre, jeton valide, ou contrôle
    désactivé par le client de test).
    """

    def dummy_get_response(request: Request) -> None:  # pragma: no cover
        return None

    check = authentication.CSRFCheck(dummy_get_response)
    # Renseigne request.META["CSRF_COOKIE"], lu par process_view().
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        # Le motif reprend des valeurs choisies par le client (en-têtes Origin ou
        # Referer) et request.path est décodé (%0A devient un saut de ligne) :
        # échappés comme le fait Django pour ses propres refus CSRF
        # (django.utils.log.log_response), pour qu'aucune ligne ne puisse être
        # forgée dans le journal.
        security_logger.warning(
            "Forbidden (%s): %s", escape_log_value(reason), escape_log_value(request.path)
        )
        return reason
    return None


def escape_log_value(value: str) -> str:
    """Neutralise les caractères de contrôle (sauts de ligne compris) d'une valeur journalisée."""
    return value.encode("unicode_escape").decode("ascii")


class SessionAuthentication(authentication.SessionAuthentication):
    def authenticate_header(self, request: Request) -> str:
        return SESSION_AUTH_SCHEME

    def enforce_csrf(self, request: Request) -> None:
        if csrf_rejection_reason(request) is not None:
            raise CsrfFailed()
