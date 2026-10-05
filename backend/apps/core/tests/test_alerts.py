"""Alertes minimales aux opérateurs (décision D17)."""

import logging

import pytest
from django.core import mail
from django.test import RequestFactory
from django.urls import resolve

from apps.core.alerts import OperatorAlertHandler, notify_operators

pytestmark = pytest.mark.django_db


@pytest.fixture
def operators(settings):
    settings.ADMINS = [("Opérateur", "ops@example.org")]
    settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR = 2


def test_no_operator_configured_sends_nothing(settings):
    settings.ADMINS = []
    assert notify_operators("Sujet", {"a": "b"}) is False
    assert mail.outbox == []


def test_alerts_are_capped_per_hour(operators):
    assert notify_operators("Un", {}) is True
    assert notify_operators("Deux", {}) is True
    assert notify_operators("Trois", {}) is False
    assert [message.subject for message in mail.outbox] == ["[GEST-CONF] Un", "[GEST-CONF] Deux"]


def test_request_error_alert_has_no_request_details(operators):
    """D17 : type d'exception, route, méthode, identifiant de requête ; ni chemin brut
    (il pourrait porter un jeton), ni en-têtes, ni cookies, ni corps."""
    request = RequestFactory().post(
        "/v1/health?jeton=SECRET-DANS-L-URL",
        data={"password": "SECRET-DANS-LE-CORPS"},
        HTTP_COOKIE="sessionid=SECRET-COOKIE",
        HTTP_AUTHORIZATION="SECRET-EN-TETE",
    )
    request.request_id = "f" * 32
    request.resolver_match = resolve("/v1/health")
    try:
        raise ValueError("détail SECRET de l'exception")
    except ValueError:
        logging.getLogger("tests.alerts").addHandler(handler := OperatorAlertHandler())
        try:
            logging.getLogger("tests.alerts").exception(
                "Erreur", extra={"request": request, "status_code": 500}
            )
        finally:
            logging.getLogger("tests.alerts").removeHandler(handler)
    assert len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert "builtins.ValueError" in body
    assert "health" in body
    assert "POST" in body
    assert "f" * 32 in body
    assert "500" in body
    assert "SECRET" not in body
    assert "SECRET" not in mail.outbox[0].subject


def test_request_errors_are_routed_to_operator_handler(settings):
    handlers = settings.LOGGING["loggers"]["django.request"]["handlers"]
    assert "operators" in handlers
    handler = settings.LOGGING["handlers"]["operators"]
    assert handler["()"] == "apps.core.alerts.OperatorAlertHandler"
