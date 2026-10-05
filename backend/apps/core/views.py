import logging
import secrets
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import caches
from django.db import DatabaseError, connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.authentication import CsrfFailed
from apps.core.errors import ErrorCode
from apps.core.exceptions import error_payload
from apps.core.http import client_ip
from apps.core.models import CronHeartbeat
from apps.core.serializers import HealthSerializer, HealthStatus, JobsStatus, ServiceStatus
from apps.core.throttling import THROTTLE_CACHE_ALIAS

logger = logging.getLogger(__name__)

# Durée de vie de la clé écrite par la sonde : elle est supprimée aussitôt, ce
# délai ne sert que si la suppression échoue (la purge des entrées expirées s'en charge).
HEALTH_CACHE_TIMEOUT = 60

# Caches sondés par /health : les deux tables créées par « createcachetable ».
HEALTH_CACHE_ALIASES = ("default", THROTTLE_CACHE_ALIAS)

# Résultat de la sonde du cache gardé en mémoire, par processus, pendant ce délai.
# /health est public et sans limite de débit : sans cette mémoire, chaque appel
# coûterait plusieurs écritures en base (INSERT, DELETE, et le SELECT COUNT(*) qui
# précède chaque écriture du DatabaseCache), amplificateur de charge facile à
# solliciter sur l'hébergement mutualisé. Le nombre d'écritures dues à la sonde est
# ainsi borné à une série par processus Passenger et par période, quel que soit le
# trafic. Contrepartie : une panne du cache est signalée avec au plus ce retard.
HEALTH_CACHE_PROBE_TTL = 10.0

_cache_probe_lock = threading.Lock()
_cache_probe: tuple[float, bool] | None = None  # (instant monotone, résultat)


def database_is_available() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.exception("Base de données injoignable")
        return False
    return True


def cache_is_available() -> bool:
    """Écrit puis relit une clé courte et unique dans chaque cache partagé, puis la supprime.

    Clé unique par appel : deux sondes simultanées (deux processus Passenger)
    ne peuvent pas se gêner.
    """
    for alias in HEALTH_CACHE_ALIASES:
        store = caches[alias]
        key = f"health:{secrets.token_hex(8)}"
        token = secrets.token_hex(8)
        try:
            store.set(key, token, timeout=HEALTH_CACHE_TIMEOUT)
            ok = store.get(key) == token
            store.delete(key)
        except Exception:
            # Toute erreur du cache (table absente, base injoignable...) : état « error ».
            logger.exception("Cache partagé « %s » indisponible", alias)
            return False
        if not ok:
            logger.error("Cache « %s » : valeur relue différente de la valeur écrite", alias)
            return False
    return True


def cache_probe_result() -> bool:
    """Résultat de ``cache_is_available``, mémorisé ``HEALTH_CACHE_PROBE_TTL`` secondes."""
    global _cache_probe
    with _cache_probe_lock:
        now = time.monotonic()
        if _cache_probe is None or now - _cache_probe[0] >= HEALTH_CACHE_PROBE_TTL:
            _cache_probe = (now, cache_is_available())
        return _cache_probe[1]


def reset_cache_probe() -> None:
    """Oublie le résultat mémorisé de la sonde (tests)."""
    global _cache_probe
    with _cache_probe_lock:
        _cache_probe = None


# Nombre d'intervalles du cron sans passage réussi de run_jobs au-delà duquel la file
# est déclarée en retard (plan L1 §8.4).
JOBS_LATE_INTERVALS = 3


def jobs_status() -> JobsStatus:
    """État de la file d'après le battement de cœur de ``run_jobs``."""
    try:
        last_success = (
            CronHeartbeat.objects.filter(name="run_jobs")
            .values_list("last_success_at", flat=True)
            .first()
        )
    except DatabaseError:
        logger.exception("Battement de cœur de run_jobs illisible")
        return JobsStatus.UNKNOWN
    if last_success is None:
        return JobsStatus.UNKNOWN
    late_after = timedelta(seconds=JOBS_LATE_INTERVALS * settings.GESTCONF_CRON_INTERVAL_SECONDS)
    return JobsStatus.LATE if timezone.now() - last_success > late_after else JobsStatus.OK


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
        cache_ok = db_ok and cache_probe_result()
        healthy = db_ok and cache_ok
        payload = {
            "status": HealthStatus.OK if healthy else HealthStatus.DEGRADED,
            "database": ServiceStatus.OK if db_ok else ServiceStatus.ERROR,
            "cache": ServiceStatus.OK if cache_ok else ServiceStatus.ERROR,
            "jobs": jobs_status() if db_ok else JobsStatus.UNKNOWN,
            "secure": request.is_secure(),
            "release": settings.GESTCONF_RELEASE,
        }
        return Response(HealthSerializer(payload).data, status=200 if healthy else 503)


@csrf_exempt
def request_diagnostics(request: HttpRequest) -> HttpResponse:
    """Diagnostic temporaire du déploiement (étape L1.0) : ce que Django voit de la requête.

    Sert à mesurer, sur o2switch, le nombre de mandataires de confiance
    (``GESTCONF_TRUSTED_PROXY_COUNT``) et le découpage SCRIPT_NAME / PATH_INFO.
    **Désactivé par défaut** : sans ``GESTCONF_DIAGNOSTICS=1``, la réponse est
    identique à celle d'une URL inconnue (404), quelle que soit la méthode.
    Ne renvoie aucun secret, aucun cookie, aucun autre en-tête. Vue Django
    simple, hors du schéma OpenAPI : elle n'est pas destinée au client Angular.
    """
    if not settings.GESTCONF_DIAGNOSTICS:
        return not_found(request)
    if request.method != "GET":
        return JsonResponse(
            error_payload(ErrorCode.METHOD_NOT_ALLOWED, _("Méthode non autorisée.")),
            status=405,
            headers={"Allow": "GET"},
        )
    meta = request.META
    payload = {
        "remote_addr": meta.get("REMOTE_ADDR", ""),
        "x_forwarded_for": meta.get("HTTP_X_FORWARDED_FOR", ""),
        "x_real_ip": meta.get("HTTP_X_REAL_IP", ""),
        "is_secure": request.is_secure(),
        "script_name": meta.get("SCRIPT_NAME", ""),
        "path_info": meta.get("PATH_INFO", ""),
        "client_ip": client_ip(request),
    }
    return JsonResponse(payload, headers={"Cache-Control": "no-store"})


# --- Gestionnaires d'erreurs Django hors DRF (URL inconnue, erreur serveur, CSRF) ---
# L'application ne sert que de l'API : les erreurs sont aussi renvoyées en JSON.


def bad_request(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload(ErrorCode.BAD_REQUEST, _("Requête invalide.")), status=400)


def permission_denied(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload(ErrorCode.PERMISSION_DENIED, _("Accès refusé.")), status=403)


def not_found(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    return JsonResponse(error_payload(ErrorCode.NOT_FOUND, _("Ressource introuvable.")), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(
        error_payload(ErrorCode.SERVER_ERROR, _("Erreur interne du serveur.")), status=500
    )


def csrf_failure(request: HttpRequest, reason: str = "") -> JsonResponse:
    """Vue d'échec CSRF de Django (``CSRF_FAILURE_VIEW``, plan L1 §4.6, cas 1).

    Ne couvre que les vues protégées par le middleware CSRF (vues Django
    ordinaires, dont allauth) ; sous DRF, voir ``apps.core.authentication``.
    Le motif technique est déjà journalisé par le middleware
    (``django.security.csrf``) : il n'est pas renvoyé au client.
    """
    return JsonResponse(error_payload(ErrorCode.CSRF_FAILED, CsrfFailed.default_detail), status=403)
