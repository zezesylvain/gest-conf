"""Format d'erreur normalisé de l'API (étude §9.1).

Toute erreur renvoyée par l'API a la forme :
    {"code": "validation_error", "message": "...", "fields": {"title": ["..."]}}
"""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler


def error_payload(code: str, message: str, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"code": code, "message": str(message), "fields": fields or {}}


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        # Erreur non prévue : Django renvoie une 500 (voir apps.core.views.server_error).
        return None

    if isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        fields = detail if isinstance(detail, dict) else {api_settings.NON_FIELD_ERRORS_KEY: detail}
        response.data = error_payload("validation_error", _("Données invalides."), fields)
    elif isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        response.data = error_payload(code, exc.detail)
    return response
