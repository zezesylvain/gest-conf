"""Expiration absolue des sessions (décision D12, plan L1 §4.3)."""

from __future__ import annotations

import time
from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse

from apps.core.actor import Actor
from apps.core.audit import record

# Horodatage (time.time()) de la connexion, posé par le récepteur de user_logged_in.
LOGIN_AT_SESSION_KEY = "gc_login_at"


class AbsoluteSessionTimeoutMiddleware:
    """Ferme toute session authentifiée ouverte depuis plus de ``GESTCONF_SESSION_MAX_AGE``.

    Django fait glisser l'échéance d'une session à chaque enregistrement
    (réauthentification, étape 2FA, changement d'état d'un flux) : une session
    volée pourrait être prolongée indéfiniment. La limite est donc comptée depuis
    la connexion. Une session authentifiée sans horodatage (créée avant ce
    middleware) est fermée de la même façon : échec fermé.

    La requête continue en anonyme : le client reçoit 401, sous ``/api/v1/`` comme
    sous allauth. Audit ``auth.session_expired``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            login_at = request.session.get(LOGIN_AT_SESSION_KEY)
            expired = (
                not isinstance(login_at, int | float)
                or time.time() - login_at > settings.GESTCONF_SESSION_MAX_AGE
            )
            if expired:
                actor = Actor.from_request(request)
                # Le récepteur de user_logged_out ne journalise pas une déconnexion volontaire.
                request.gc_session_expired = True
                logout(request)
                record("auth.session_expired", actor=actor, obj=user)
        return self.get_response(request)
