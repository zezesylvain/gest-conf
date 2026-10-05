"""Outils des tests de comptes : appels allauth headless, lecture des liens envoyés."""

from __future__ import annotations

import time
from urllib.parse import unquote

from django.core import mail
from django.test import Client

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.tests.factories import DEFAULT_PASSWORD

# Préfixe des vues allauth, relatif au point de montage /api (config/mount.py).
AUTH = "/_allauth/browser/v1"
JSON = "application/json"
AUTH_RECORDS_SESSION_KEY = "account_authentication_methods"


def post(client: Client, path: str, data: dict | None = None, **extra):
    return client.post(f"{AUTH}/{path}", data or {}, content_type=JSON, **extra)


def signup(client: Client, email: str, password: str = DEFAULT_PASSWORD, **extra):
    return post(client, "auth/signup", {"email": email, "password": password}, **extra)


def login(client: Client, email: str, password: str = DEFAULT_PASSWORD, **extra):
    return post(client, "auth/login", {"email": email, "password": password}, **extra)


def key_from_last_email(marker: str) -> str:
    """Clé du lien (dans le fragment, encodée) du dernier e-mail envoyé contenant ``marker``."""
    for message in reversed(mail.outbox):
        if marker in message.body:
            return unquote(message.body.split(marker, 1)[1].split()[0])
    raise AssertionError(f"Aucun e-mail envoyé ne contient {marker!r}")


def flow_ids(response) -> list[str]:
    return [flow["id"] for flow in response.json()["data"].get("flows", [])]


def age_session(client: Client, *, login_seconds_ago: float = 0, auth_seconds_ago: float = 0):
    """Vieillit l'horodatage de connexion (D12) et/ou celui des authentifications."""
    session = client.session
    if login_seconds_ago:
        session[LOGIN_AT_SESSION_KEY] = time.time() - login_seconds_ago
    if auth_seconds_ago:
        records = session[AUTH_RECORDS_SESSION_KEY]
        for record in records:
            record["at"] = time.time() - auth_seconds_ago
        session[AUTH_RECORDS_SESSION_KEY] = records
    session.save()
