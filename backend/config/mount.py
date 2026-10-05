"""Gestion du préfixe de montage de l'API (/api).

En production, Passenger monte l'application sous /api : selon la norme WSGI,
il place normalement « /api » dans SCRIPT_NAME et le reste du chemin dans
PATH_INFO. Le serveur de développement, lui, transmet le chemin complet
(« /api/v1/health ») dans PATH_INFO.

Ce middleware WSGI ramène les deux cas à la même forme
(SCRIPT_NAME="/api", PATH_INFO="/v1/health") : les URL Django sont donc
déclarées sans le préfixe (« v1/... ») et reverse() le rajoute automatiquement.
Le comportement exact de Passenger sur o2switch reste à confirmer lors du
prototype de déploiement (lot L0) ; ce middleware fonctionne dans les deux cas.
"""

from collections.abc import Callable, Iterable
from typing import Any

WSGIApp = Callable[[dict[str, Any], Callable[..., Any]], Iterable[bytes]]


class MountPrefixMiddleware:
    def __init__(self, app: WSGIApp, prefix: str) -> None:
        self.app = app
        self.prefix = "/" + prefix.strip("/") if prefix.strip("/") else ""

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]):
        path = environ.get("PATH_INFO", "")
        if (
            self.prefix
            and not environ.get("SCRIPT_NAME")
            and (path == self.prefix or path.startswith(self.prefix + "/"))
        ):
            environ["SCRIPT_NAME"] = self.prefix
            environ["PATH_INFO"] = path[len(self.prefix) :] or "/"
        return self.app(environ, start_response)
