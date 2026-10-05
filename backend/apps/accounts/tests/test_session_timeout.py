"""Expiration absolue des sessions (décision D12, plan L1 §4.11, §12.1)."""

import time

import pytest

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.helpers import AUTH, age_session, login
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

TWELVE_HOURS = 12 * 3600


@pytest.fixture
def logged_in(client):
    user = VerifiedUserFactory()
    assert login(client, user.email).status_code == 200
    return user


def test_login_records_absolute_start(client, logged_in):
    assert abs(client.session[LOGIN_AT_SESSION_KEY] - time.time()) < 5


def test_absolute_session_timeout(client, logged_in):
    """Une session active à 11 h 59 est refusée à 12 h 01, quelle que soit son activité."""
    age_session(client, login_seconds_ago=TWELVE_HOURS - 60)
    assert client.get("/v1/me").status_code == 200
    age_session(client, login_seconds_ago=TWELVE_HOURS + 60)
    assert client.get("/v1/me").status_code == 401
    # Côté allauth aussi : la session est fermée.
    assert client.get(f"{AUTH}/auth/session").json()["meta"]["is_authenticated"] is False
    entry = AuditLog.objects.get(action="auth.session_expired")
    assert entry.object_id == str(logged_in.pk)
    # Une expiration n'est pas journalisée comme une déconnexion volontaire.
    assert not AuditLog.objects.filter(action="auth.logout").exists()


def test_authenticated_session_without_timestamp_is_closed(client):
    """Session ouverte avant le middleware (sans horodatage) : échec fermé."""
    user = VerifiedUserFactory()
    client.force_login(user)
    session = client.session
    session.pop(LOGIN_AT_SESSION_KEY, None)
    session.save()
    assert client.get("/v1/me").status_code == 401


def test_session_cookie_settings(settings):
    assert settings.SESSION_COOKIE_AGE == TWELVE_HOURS
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
    assert settings.SESSION_SAVE_EVERY_REQUEST is False
    assert settings.SESSION_COOKIE_HTTPONLY is True
