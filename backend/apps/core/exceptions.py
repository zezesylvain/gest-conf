"""Format d'erreur normalisé de l'API (étude §9.1, plan L1 §9.1).

Toute erreur renvoyée par l'API a la forme :
    {"code": "validation_error", "message": "...", "fields": {"title": ["..."]}}

Le champ ``code`` appartient toujours au catalogue ``ErrorCode`` : un code
inconnu est remplacé par un code générique selon le statut HTTP (et journalisé).
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.views import exception_handler

from apps.core.errors import (
    DomainError,
    ErrorCode,
    Invalid,
    NotAllowed,
    QuotaExceeded,
    RuleViolation,
)

logger = logging.getLogger(__name__)


# Code générique de repli, par statut HTTP, pour une exception dont le code
# n'appartient pas au catalogue (exception DRF personnalisée oubliée, par exemple).
_FALLBACK_CODES: dict[int, ErrorCode] = {
    status.HTTP_400_BAD_REQUEST: ErrorCode.BAD_REQUEST,
    status.HTTP_401_UNAUTHORIZED: ErrorCode.NOT_AUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.PERMISSION_DENIED,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_405_METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    status.HTTP_406_NOT_ACCEPTABLE: ErrorCode.NOT_ACCEPTABLE,
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: ErrorCode.UNSUPPORTED_MEDIA_TYPE,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.THROTTLED,
}

# Correspondance entre erreurs métier et statuts HTTP (QuotaExceeded : voir plus bas).
_DOMAIN_STATUS: tuple[tuple[type[DomainError], int], ...] = (
    (RuleViolation, status.HTTP_409_CONFLICT),
    (NotAllowed, status.HTTP_403_FORBIDDEN),
    (Invalid, status.HTTP_400_BAD_REQUEST),
)


def error_payload(
    code: ErrorCode | str, message: Any, fields: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"code": str(code), "message": str(message), "fields": fields or {}}


def catalogued_code(code: Any, http_status: int) -> ErrorCode:
    """Ramène ``code`` dans le catalogue ; sinon, code générique selon le statut."""
    if isinstance(code, str) and code in ErrorCode.values:
        return ErrorCode(code)
    logger.error("Code d'erreur hors catalogue %r (statut %s)", code, http_status)
    if http_status >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return ErrorCode.SERVER_ERROR
    return _FALLBACK_CODES.get(http_status, ErrorCode.BAD_REQUEST)


def domain_error_to_api_exception(error: DomainError) -> exceptions.APIException:
    """Traduit une erreur métier en exception DRF (statut, message, code)."""
    if isinstance(error, QuotaExceeded):
        # Throttled pose l'en-tête Retry-After et garde le code « throttled ».
        return exceptions.Throttled(wait=error.retry_after, detail=str(error.message))
    # DomainError sans sous-classe connue : refus générique (400), jamais une 500.
    http_status = next(
        (code for error_class, code in _DOMAIN_STATUS if isinstance(error, error_class)),
        status.HTTP_400_BAD_REQUEST,
    )
    api_exception = exceptions.APIException(detail=str(error.message), code=error.code.value)
    api_exception.status_code = http_status
    return api_exception


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    domain_error = exc if isinstance(exc, DomainError) else None
    if domain_error is not None:
        exc = domain_error_to_api_exception(domain_error)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()

    response = exception_handler(exc, context)
    if response is None:
        # Erreur non prévue : Django renvoie une 500 (voir apps.core.views.server_error).
        return None

    if domain_error is not None:
        fields = {
            name: [str(message) for message in messages]
            for name, messages in domain_error.fields.items()
        }
        response.data = error_payload(domain_error.code, exc.detail, fields)
    elif isinstance(exc, exceptions.ValidationError):
        detail = exc.detail
        fields = detail if isinstance(detail, dict) else {api_settings.NON_FIELD_ERRORS_KEY: detail}
        response.data = error_payload(ErrorCode.VALIDATION_ERROR, _("Données invalides."), fields)
    elif isinstance(exc, exceptions.APIException):
        codes = exc.get_codes()
        code = codes if isinstance(codes, str) else exc.default_code
        response.data = error_payload(catalogued_code(code, response.status_code), exc.detail)
    return response
