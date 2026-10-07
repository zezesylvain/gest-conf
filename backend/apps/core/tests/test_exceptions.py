"""Format d'erreur normalisé {code, message, fields} (étude §9.1, plan L1 §9.1)."""

import json

import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from django.test import RequestFactory
from rest_framework import exceptions

from apps.core import views
from apps.core.authentication import CsrfFailed
from apps.core.errors import (
    DomainError,
    ErrorCode,
    Invalid,
    NotAllowed,
    QuotaExceeded,
    RuleViolation,
)
from apps.core.exceptions import api_exception_handler, catalogued_code

pytestmark = [pytest.mark.urls("apps.core.tests.urls"), pytest.mark.django_db]


def assert_error_shape(payload: dict) -> None:
    assert set(payload) == {"code", "message", "fields"}
    assert isinstance(payload["message"], str) and payload["message"]
    assert payload["code"] in ErrorCode.values


def test_field_validation_error(client):
    response = client.post("/field-validation", {}, content_type="application/json")
    assert response.status_code == 400
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "validation_error"
    assert list(payload["fields"]) == ["title"]


def test_non_field_validation_error(client):
    response = client.post("/non-field-validation", {}, content_type="application/json")
    assert response.status_code == 400
    payload = response.json()
    assert payload["fields"] == {"non_field_errors": ["Erreur globale"]}


def test_unauthenticated_access(client):
    """Session absente : 401 (et non 403) avec l'en-tête WWW-Authenticate (plan L1 §9.1, D4)."""
    response = client.get("/protected")
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Session"
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "not_authenticated"
    assert payload["fields"] == {}


def test_authenticated_access(auth_client, user):
    response = auth_client.get("/protected")
    assert response.status_code == 200
    assert response.json() == {"user": user.email}


def test_http404_is_normalized(client):
    response = client.get("/http404")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_django_permission_denied_is_normalized(client):
    response = client.get("/django-permission-denied")
    assert response.status_code == 403
    assert response.json()["code"] == "permission_denied"


def test_malformed_json_is_parse_error(client):
    response = client.post("/echo", "{pas du json", content_type="application/json")
    assert response.status_code == 400
    assert response.json()["code"] == "parse_error"


def test_unsupported_media_type(client):
    response = client.post("/echo", "texte", content_type="text/plain")
    assert response.status_code == 415
    assert response.json()["code"] == "unsupported_media_type"


def test_method_not_allowed(client):
    response = client.delete("/echo")
    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_not_acceptable(client):
    response = client.get("/http404", HTTP_ACCEPT="application/xml")
    assert response.status_code == 406
    assert response.json()["code"] == "not_acceptable"


@pytest.mark.parametrize(
    "accept",
    [
        "application/octet-stream",
        "application/pdf",
        "text/csv",
        "text/calendar",
        "image/png",
        "image/svg+xml",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ],
)
def test_file_request_falls_back_to_json_errors(client, accept):
    """Le client généré annonce le type du fichier attendu : pas de 406 avant la vue, et
    une erreur garde le format normalisé, en JSON (bilan de L8.10)."""
    response = client.get("/http404", HTTP_ACCEPT=accept)
    assert response.status_code == 404
    assert response["Content-Type"] == "application/json"
    assert_error_shape(response.json())


def test_mixed_accept_with_unserved_type_stays_not_acceptable(client):
    response = client.get("/http404", HTTP_ACCEPT="text/csv, application/xml")
    assert response.status_code == 406


# --- Erreurs métier (DomainError) ---------------------------------------------------


def test_rule_violation_is_409_with_code_and_fields(client):
    response = client.get("/domain-error/rule")
    assert response.status_code == 409
    assert response.json() == {
        "code": "in_use",
        "message": "Cet objet est utilisé ailleurs.",
        "fields": {"track": ["Déjà utilisé."]},
    }


def test_not_allowed_is_403_permission_denied(client):
    response = client.get("/domain-error/not-allowed")
    assert response.status_code == 403
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "permission_denied"
    assert payload["message"] == "Action non autorisée."


def test_invalid_is_400_validation_error_with_fields(client):
    response = client.get("/domain-error/invalid")
    assert response.status_code == 400
    assert response.json() == {
        "code": "validation_error",
        "message": "Données invalides.",
        "fields": {"end": ["Doit suivre le début."]},
    }


def test_quota_exceeded_is_429_throttled_with_retry_after(client):
    """QuotaExceeded passe par Throttled de DRF : en-tête Retry-After arrondi au-dessus."""
    response = client.get("/domain-error/quota")
    assert response.status_code == 429
    assert response["Retry-After"] == "43"
    payload = response.json()
    assert_error_shape(payload)
    assert payload["code"] == "throttled"
    assert payload["message"].startswith("Quota atteint.")


def test_domain_errors_are_http_agnostic():
    """Les erreurs métier ne portent ni statut ni dépendance à DRF (plan L1 §9.1)."""
    for error_class in (DomainError, RuleViolation, NotAllowed, Invalid, QuotaExceeded):
        assert not hasattr(error_class, "status_code")
        assert not issubclass(error_class, exceptions.APIException)


def test_rule_violation_requires_a_code():
    with pytest.raises(TypeError, match="code"):
        RuleViolation("Sans code")


def test_domain_error_code_must_belong_to_catalogue():
    with pytest.raises(ValueError, match="code_inconnu"):
        RuleViolation("Code inventé", code="code_inconnu")


def test_quota_exceeded_requires_positive_retry_after():
    with pytest.raises(ValueError, match="retry_after"):
        QuotaExceeded(retry_after=0)


# --- Catalogue de codes ------------------------------------------------------------

# Toutes les exceptions que l'API peut produire aujourd'hui, par le gestionnaire.
HANDLED_EXCEPTIONS = [
    exceptions.ValidationError({"title": ["obligatoire"]}),
    exceptions.ParseError(),
    exceptions.NotAuthenticated(),
    exceptions.PermissionDenied(),
    exceptions.NotFound(),
    exceptions.MethodNotAllowed("DELETE"),
    exceptions.NotAcceptable(),
    exceptions.UnsupportedMediaType("text/plain"),
    exceptions.Throttled(wait=10),
    CsrfFailed(),
    Http404(),
    DjangoPermissionDenied(),
    RuleViolation(code=ErrorCode.IN_USE),
    NotAllowed(),
    Invalid(),
    QuotaExceeded(retry_after=5),
    # Exceptions dont le code n'appartient pas au catalogue : code de repli.
    exceptions.AuthenticationFailed(),
    exceptions.APIException(),
    exceptions.PermissionDenied(code="code_maison"),
]


@pytest.mark.parametrize("exc", HANDLED_EXCEPTIONS, ids=lambda exc: type(exc).__name__)
def test_every_code_emitted_by_handler_is_in_catalogue(exc):
    response = api_exception_handler(exc, {})
    assert response is not None
    assert_error_shape(response.data)


def test_unknown_code_falls_back_by_status(caplog):
    assert catalogued_code("code_maison", 403) == ErrorCode.PERMISSION_DENIED
    assert catalogued_code("error", 500) == ErrorCode.SERVER_ERROR
    assert catalogued_code("authentication_failed", 401) == ErrorCode.NOT_AUTHENTICATED
    assert catalogued_code("autre", 418) == ErrorCode.BAD_REQUEST
    assert "hors catalogue" in caplog.text


def test_django_error_views_use_catalogue_codes():
    request = RequestFactory().get("/")
    responses = [
        views.bad_request(request),
        views.permission_denied(request),
        views.not_found(request),
        views.server_error(request),
        views.csrf_failure(request, reason="CSRF cookie not set."),
    ]
    for response in responses:
        assert_error_shape(json.loads(response.content))


def test_unexpected_exception_is_left_to_django():
    """Erreur imprévue : le gestionnaire s'abstient, Django renvoie la 500 JSON (server_error)."""
    assert api_exception_handler(ValueError("imprévu"), {}) is None
