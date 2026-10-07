"""Alerte minimale aux opérateurs (D17) : contenu minimal, plafond, indépendance de la base."""

import logging

import pytest
from django.conf import settings
from django.core import mail
from django.db import OperationalError, connection
from django.http import HttpResponse
from django.test import Client
from django.urls import path

from apps.core import alerts
from apps.core.alerts import OperatorAlertHandler, send_operator_alert, take_alert_slot

SECRET_COOKIE = "cookie-tres-secret"
SECRET_HEADER = "en-tete-secret"
SECRET_PARAM = "parametre-secret"
SECRET_BODY = "corps-secret"
SECRET_MESSAGE = "jean.dupont@univ.ci a provoqué l'erreur"


def failing_view(request, anything=""):
    raise ZeroDivisionError(SECRET_MESSAGE)


def database_failure_view(request):
    raise OperationalError("(2006, 'MySQL server has gone away')")


def ok_view(request):
    return HttpResponse("ok")


urlpatterns = [
    path("boom/<str:anything>", failing_view),
    path("db-down", database_failure_view),
    path("ok", ok_view),
]
handler500 = "apps.core.views.server_error"


@pytest.fixture
def client_500():
    return Client(raise_request_exception=False)


def _boom(client, suffix="x"):
    return client.post(
        f"/boom/{suffix}?token={SECRET_PARAM}",
        data=f'{{"password": "{SECRET_BODY}"}}',
        content_type="application/json",
        HTTP_COOKIE=f"sessionid={SECRET_COOKIE}",
        HTTP_X_CUSTOM=SECRET_HEADER,
    )


def test_handler_is_wired_on_django_request():
    handlers = settings.LOGGING["loggers"]["django.request"]["handlers"]
    assert handlers == ["operator_alert"]
    configured = [
        handler
        for handler in logging.getLogger("django.request").handlers
        if isinstance(handler, OperatorAlertHandler)
    ]
    assert len(configured) == 1
    assert configured[0].level == logging.ERROR


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_server_error_sends_a_minimal_alert(client_500, operator_emails):
    response = _boom(client_500)
    assert response.status_code == 500
    assert response.json()["code"] == "server_error"
    assert len(mail.outbox) == 1
    alert = mail.outbox[0]
    assert alert.to == operator_emails
    assert "ZeroDivisionError" in alert.subject
    content = alert.subject + alert.body
    for expected in ("ZeroDivisionError", "/boom/x", "POST", response["X-Request-ID"], "UTC"):
        assert expected in content
    # Jamais le corps, les en-têtes, les cookies, les paramètres ni le message.
    for secret in (SECRET_COOKIE, SECRET_HEADER, SECRET_PARAM, SECRET_BODY, "jean", "Traceback"):
        assert secret not in content
    assert alert.attachments == []
    assert not getattr(alert, "alternatives", [])


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_no_alert_without_operator_addresses(client_500, settings):
    settings.GESTCONF_OPERATOR_EMAILS = []
    assert _boom(client_500).status_code == 500
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_no_alert_for_client_errors_or_handled_5xx(client, operator_emails, monkeypatch):
    """404 (avertissement) et /health en 503 (réponse voulue, sans exception) : pas d'alerte."""
    from apps.core import views

    client.get("/inexistant")
    monkeypatch.setattr(views, "database_is_available", lambda: False)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(settings, "ROOT_URLCONF", "config.urls")
        assert Client().get("/v1/health").status_code == 503
    assert mail.outbox == []


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_alert_path_is_escaped_and_bounded(client_500, operator_emails):
    _boom(client_500, "a%0Ab" + "x" * 500)
    body = mail.outbox[0].body
    assert "a\\nb" in body
    assert all(len(line) < 260 for line in body.splitlines())


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_alerts_are_capped_per_hour(client_500, operator_emails, settings):
    settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR = 3
    for _ in range(5):
        assert _boom(client_500).status_code == 500
    assert len(mail.outbox) == 3


def test_cap_window_slides_and_reports_suppressed_alerts(settings):
    settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR = 2
    assert take_alert_slot(now=1000.0) == (True, 0)
    assert take_alert_slot(now=1001.0) == (True, 0)
    assert take_alert_slot(now=1002.0) == (False, 1)
    assert take_alert_slot(now=1003.0) == (False, 2)
    # Une heure plus tard, la première sort de la fenêtre ; 2 alertes avaient été retenues.
    assert take_alert_slot(now=4600.5) == (True, 2)
    assert take_alert_slot(now=4601.5) == (True, 0)


def test_cap_is_shared_through_the_state_file(settings):
    """Le plafond vaut pour tous les processus : état dans un fichier verrouillé."""
    settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR = 1
    assert take_alert_slot(now=1000.0) == (True, 0)
    alerts.reset_memory_state()  # un autre processus n'a pas cette mémoire
    assert take_alert_slot(now=1001.0) == (False, 1)
    assert (settings.GESTCONF_LOCK_DIR / alerts.STATE_FILE_NAME).is_file()


def test_cap_falls_back_to_memory_when_state_file_is_unusable(settings, tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("x")
    settings.GESTCONF_LOCK_DIR = blocker / "sous-dossier"
    settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR = 1
    assert take_alert_slot(now=1000.0) == (True, 0)
    assert take_alert_slot(now=1001.0) == (False, 1)


def test_corrupted_state_file_is_reset(settings):
    settings.GESTCONF_LOCK_DIR.mkdir(parents=True, exist_ok=True)
    (settings.GESTCONF_LOCK_DIR / alerts.STATE_FILE_NAME).write_text("{pas du json")
    assert take_alert_slot(now=1000.0) == (True, 0)


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_database_failure_still_alerts(client_500, operator_emails, monkeypatch):
    """Une erreur de base n'empêche pas l'alerte : aucun accès à la base pour l'envoyer."""

    def no_database(*args, **kwargs):
        raise AssertionError("l'alerte ne doit pas toucher à la base")

    monkeypatch.setattr(connection, "cursor", no_database)
    response = client_500.get("/db-down")
    assert response.status_code == 500
    assert len(mail.outbox) == 1
    assert "OperationalError" in mail.outbox[0].subject


@pytest.mark.django_db
@pytest.mark.urls(__name__)
def test_failing_alert_does_not_cause_a_new_error(client_500, operator_emails, settings, caplog):
    """Fournisseur en panne : la réponse 500 part normalement, rien ne remonte."""
    settings.EMAIL_BACKEND = "apps.communications.backends.UnconfiguredEmailBackend"
    response = _boom(client_500)
    assert response.status_code == 500
    assert response.json()["code"] == "server_error"
    assert "Alerte aux opérateurs impossible" in caplog.text


def test_send_operator_alert_never_raises(operator_emails, monkeypatch):
    def broken_slot(now=None):
        raise RuntimeError("inattendu")

    monkeypatch.setattr(alerts, "take_alert_slot", broken_slot)
    assert send_operator_alert("Sujet", [("Clé", "valeur")]) is False


def test_send_operator_alert_is_not_reentrant(operator_emails):
    """Une alerte déclenchée pendant l'envoi d'une autre (erreur journalisée par le backend,
    par exemple) est ignorée : pas de boucle."""
    alerts._reentrancy.active = True
    try:
        assert send_operator_alert("Sujet", []) is False
    finally:
        alerts._reentrancy.active = False
    assert mail.outbox == []


def test_handler_ignores_records_without_exception(operator_emails):
    handler = OperatorAlertHandler()
    record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "msg", (), None)
    handler.emit(record)
    assert mail.outbox == []


def test_alert_subject_has_site_name_and_no_personal_data(operator_emails):
    assert send_operator_alert("Tâche en échec définitif", [("Tâche", "#3")]) is True
    assert mail.outbox[0].subject == f"[{settings.GESTCONF_SITE_NAME}] Tâche en échec définitif"
    assert mail.outbox[0].from_email == settings.DEFAULT_FROM_EMAIL
