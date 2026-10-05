"""En-têtes posés sur toutes les réponses de l'API (plan L1 §4.6, §7.2)."""

import re

import pytest
from django.http import HttpResponse
from django.test import Client

from apps.core.middleware import RequestIdMiddleware

pytestmark = pytest.mark.django_db

# Réponses de natures différentes : vue DRF, vue d'erreur Django (URL inconnue), vue
# Django simple (diagnostic désactivé).
PATHS = [("get", "/v1/health"), ("get", "/v1/inconnu"), ("post", "/v1/diagnostics/request")]


@pytest.mark.parametrize(("method", "path"), PATHS)
def test_every_response_has_robots_tag(method, path):
    response = getattr(Client(enforce_csrf_checks=True), method)(path)
    assert response["X-Robots-Tag"] == "noindex, nofollow"


@pytest.mark.parametrize(("method", "path"), PATHS)
def test_every_response_has_request_id(method, path):
    response = getattr(Client(enforce_csrf_checks=True), method)(path)
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


@pytest.mark.urls("apps.core.tests.urls")
def test_response_produced_by_csrf_middleware_has_headers():
    """Refus produit par le middleware CSRF, avant toute vue : en-têtes posés quand même."""
    response = Client(enforce_csrf_checks=True).post("/csrf-django-view")
    assert response.status_code == 403
    assert response["X-Robots-Tag"] == "noindex, nofollow"
    assert re.fullmatch(r"[0-9a-f]{32}", response["X-Request-ID"])


def test_request_id_is_unique_and_not_taken_from_client(client):
    first = client.get("/v1/health", HTTP_X_REQUEST_ID="forge")
    second = client.get("/v1/health")
    assert first["X-Request-ID"] != "forge"
    assert first["X-Request-ID"] != second["X-Request-ID"]


def test_request_id_is_available_on_request(rf):
    seen = {}

    def view(request):
        seen["id"] = request.request_id
        return HttpResponse()

    response = RequestIdMiddleware(view)(rf.get("/"))
    assert response["X-Request-ID"] == seen["id"]
