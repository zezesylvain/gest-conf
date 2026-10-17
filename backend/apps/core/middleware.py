"""Middlewares transverses de l'API."""

import uuid
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.translation import gettext as _

from apps.core.errors import ErrorCode
from apps.core.exceptions import error_payload

REQUEST_ID_HEADER = "X-Request-ID"
ROBOTS_TAG_HEADER = "X-Robots-Tag"
ROBOTS_TAG_VALUE = "noindex, nofollow"


class RequestIdMiddleware:
    """Attribue un identifiant à chaque requête (``request.request_id``, uuid4 hexadécimal).

    Renvoyé dans l'en-tête ``X-Request-ID`` et repris par le journal d'audit,
    pour corréler une plainte, une trace d'audit et les journaux du serveur.
    Un identifiant fourni par le client n'est jamais repris : il pourrait être
    forgé pour brouiller la corrélation.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.request_id = uuid.uuid4().hex
        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request.request_id
        return response


class RobotsTagMiddleware:
    """Interdit l'indexation de toutes les réponses de l'API (plan L1 §4.6)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response[ROBOTS_TAG_HEADER] = ROBOTS_TAG_VALUE
        return response


class RequestSizeLimitMiddleware:
    """Refuse (413) une requête dont le corps annoncé dépasse ``GESTCONF_MAX_REQUEST_MB``,
    avant toute lecture (revue de sécurité L9.5, ASVS V12.1). Sans cette borne, un envoi de
    plusieurs gigaoctets remplissait le dossier temporaire ou la mémoire avant le contrôle de
    taille de chaque vue. Le plafond couvre le plus gros dépôt permis (50 Mio, plan L3).
    Sous WSGI, un corps sans ``Content-Length`` n'est pas lu par Django."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length > settings.GESTCONF_MAX_REQUEST_MB * 1024 * 1024:
            return JsonResponse(
                error_payload(ErrorCode.BAD_REQUEST, _("Requête trop volumineuse.")),
                status=413,
                headers={"Cache-Control": "no-store"},
            )
        return self.get_response(request)


class DefaultNoStoreMiddleware:
    """``Cache-Control: no-store`` sur toute réponse qui n'en fixe pas (revue de sécurité
    L9.5, ASVS V8.2.1) : les données personnelles de l'API ne restent ni dans le cache du
    navigateur ni dans un cache intermédiaire. Les vues publiques et les fichiers fixent le
    leur (bandeau, édition courante, pièces)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if not response.has_header("Cache-Control"):
            response["Cache-Control"] = "no-store"
        return response
