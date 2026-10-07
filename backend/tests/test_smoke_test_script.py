"""deploy/smoke-test.sh, contrôle de la file de tâches (champ ``jobs`` de /health, L1.2).

Le script est exécuté pour de bon contre un petit serveur HTTP local qui imite /api/v1/health ;
seule la ligne du contrôle ``jobs`` est examinée (les contrôles du portail et de la gestion
échouent ici, faute de pages, et ne sont pas concernés).
"""

from __future__ import annotations

import shutil
import subprocess
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from django.conf import settings

SMOKE_SCRIPT = Path(settings.BASE_DIR).parent / "deploy" / "smoke-test.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    BASH is None or shutil.which("curl") is None, reason="bash ou curl absent"
)


class FakeApi(BaseHTTPRequestHandler):
    """/api/v1/health renvoie ``server.health_body`` ; tout le reste, 404 JSON."""

    def do_GET(self) -> None:
        if self.path == "/api/v1/health":
            body = self.server.health_body  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
        else:
            body = b'{"code":"not_found","message":"Ressource introuvable.","fields":{}}'
            self.send_response(404)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Pas de journal d'accès dans la sortie des tests."""


@pytest.fixture
def fake_api() -> Iterator[ThreadingHTTPServer]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApi)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def run_smoke(server: ThreadingHTTPServer, body: str, **extra_env: str) -> list[str]:
    server.health_body = body.encode()  # type: ignore[attr-defined]
    host, port = server.server_address[:2]
    result = subprocess.run(  # noqa: S603  # arguments maîtrisés par le test
        [BASH, str(SMOKE_SCRIPT), f"http://{host}:{port}"],
        # Environnement réduit : aucun mandataire HTTP hérité ne s'interpose.
        env={"PATH": "/usr/bin:/bin", **extra_env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return result.stdout.splitlines()


def jobs_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "jobs" in line]


HEALTH_OK = (
    '{"status":"ok","database":"ok","cache":"ok","jobs":"ok","secure":false,"release":"dev"}'
)


@pytest.mark.parametrize(
    "body",
    [
        HEALTH_OK,
        # Tolérance aux espaces autour de « : » (comme les autres contrôles JSON).
        '{"status" : "ok", "database" : "ok", "cache" : "ok", "jobs" :  "ok"}',
    ],
)
def test_smoke_accepts_jobs_ok(fake_api, body):
    [line] = jobs_lines(run_smoke(fake_api, body))
    assert line.lstrip().startswith("OK")


def test_smoke_accepts_jobs_unknown_right_after_a_deployment(fake_api):
    """Aucun passage de run_jobs encore enregistré : accepté, avec une note."""
    body = '{"status": "ok", "database": "ok", "cache": "ok", "jobs": "unknown"}'
    check, note = jobs_lines(run_smoke(fake_api, body))
    assert check.lstrip().startswith("OK")
    assert note.lstrip().startswith("NOTE")


@pytest.mark.parametrize(
    "body",
    [
        '{"status":"degraded","database":"ok","cache":"ok","jobs":"late"}',
        '{"status" : "degraded", "jobs" : "late"}',
        # Backend antérieur à L1.2 (pas de champ jobs) : échec également.
        '{"status":"ok","database":"ok","cache":"ok"}',
    ],
)
def test_smoke_fails_when_jobs_are_late_or_missing(fake_api, body):
    [line] = jobs_lines(run_smoke(fake_api, body))
    assert line.lstrip().startswith("ÉCHEC")


def test_smoke_can_require_jobs_ok(fake_api):
    """SMOKE_REQUIRE_JOBS_OK=1 (jalon J-tech) : « unknown » ne suffit plus."""
    unknown = HEALTH_OK.replace('"jobs":"ok"', '"jobs":"unknown"')
    [line] = jobs_lines(run_smoke(fake_api, unknown, SMOKE_REQUIRE_JOBS_OK="1"))
    assert line.lstrip().startswith("ÉCHEC")
    [line] = jobs_lines(run_smoke(fake_api, HEALTH_OK, SMOKE_REQUIRE_JOBS_OK="1"))
    assert line.lstrip().startswith("OK")
