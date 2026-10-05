"""Montage de l'API sous /api (config/mount.py)."""

import io

import pytest
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from django.urls import set_script_prefix

from config.mount import MountPrefixMiddleware


def _call(middleware, **environ):
    seen = {}

    def app(env, start_response):
        seen.update(env)
        return []

    middleware.app = app
    middleware(environ, lambda *args: None)
    return seen.get("SCRIPT_NAME", ""), seen.get("PATH_INFO", "")


@pytest.mark.parametrize(
    ("script_name", "path_info", "expected"),
    [
        # Serveur de développement : chemin complet dans PATH_INFO.
        ("", "/api/v1/health", ("/api", "/v1/health")),
        ("", "/api", ("/api", "/")),
        # Passenger conforme WSGI : préfixe déjà dans SCRIPT_NAME, rien à faire.
        ("/api", "/v1/health", ("/api", "/v1/health")),
        # Chemins hors préfixe ou simplement ressemblants : inchangés.
        ("", "/apiv1/health", ("", "/apiv1/health")),
        ("", "/v1/health", ("", "/v1/health")),
    ],
)
def test_prefix_is_moved_to_script_name(script_name, path_info, expected):
    middleware = MountPrefixMiddleware(app=None, prefix="/api")
    assert _call(middleware, SCRIPT_NAME=script_name, PATH_INFO=path_info) == expected


def test_empty_prefix_disables_middleware():
    middleware = MountPrefixMiddleware(app=None, prefix="")
    assert _call(middleware, SCRIPT_NAME="", PATH_INFO="/api/v1/health") == ("", "/api/v1/health")


@pytest.fixture
def wsgi_call():
    """Appelle l'application WSGI réelle (config.wsgi), comme Passenger."""
    from config.wsgi import application

    def call(script_name: str, path_info: str) -> str:
        environ = {
            "REQUEST_METHOD": "GET",
            "SCRIPT_NAME": script_name,
            "PATH_INFO": path_info,
            "SERVER_NAME": "testserver",
            "SERVER_PORT": "80",
            "HTTP_HOST": "testserver",
            "wsgi.url_scheme": "http",
            "wsgi.input": io.BytesIO(),
            "wsgi.errors": io.StringIO(),
        }
        status = []
        application(environ, lambda s, headers, exc_info=None: status.append(s))
        return status[0]

    # Comme le client de test Django : ne pas fermer la connexion à la base au
    # milieu de la transaction du test (sans effet sur SQLite, fatal sur MariaDB).
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    yield call
    request_started.connect(close_old_connections)
    request_finished.connect(close_old_connections)
    # Le gestionnaire WSGI mémorise le préfixe pour le fil d'exécution : on le remet.
    set_script_prefix("/")


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("script_name", "path_info"),
    [("", "/api/v1/health"), ("/api", "/v1/health")],
)
def test_health_is_reachable_through_wsgi_entry_point(wsgi_call, script_name, path_info):
    assert wsgi_call(script_name, path_info).startswith("200")
