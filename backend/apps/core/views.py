import logging

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import error_payload
from apps.core.serializers import HealthSerializer

logger = logging.getLogger(__name__)


def database_is_available() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Base de données injoignable")
        return False
    return True


class HealthView(APIView):
    """Sonde de disponibilité (supervision externe et tests de fumée du déploiement)."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="health",
        responses={200: HealthSerializer, 503: HealthSerializer},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        db_ok = database_is_available()
        payload = {
            "status": "ok" if db_ok else "degraded",
            "database": "ok" if db_ok else "error",
            "secure": request.is_secure(),
            "release": settings.GESTCONF_RELEASE,
        }
        return Response(HealthSerializer(payload).data, status=200 if db_ok else 503)


# --- Gestionnaires d'erreurs Django hors DRF (URL inconnue, erreur serveur) ---------
# L'application ne sert que de l'API : les erreurs sont aussi renvoyées en JSON.


def bad_request(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload("bad_request", _("Requête invalide.")), status=400)


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload("permission_denied", _("Accès refusé.")), status=403)


def not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload("not_found", _("Ressource introuvable.")), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(error_payload("server_error", _("Erreur interne du serveur.")), status=500)
