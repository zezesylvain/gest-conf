"""Middlewares transverses de l'API."""

import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

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
