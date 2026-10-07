"""deploy/cron.sh : point d'entrée des tâches cron (plan L1 §8.4, règle n° 9 de CLAUDE.md).

Le script est exécuté pour de bon, dans une arborescence qui reproduit celle du serveur :
``~/gestconf-app/deploy/cron.sh``, ``~/gestconf-app/.env``, venv cPanel
``~/virtualenv/gestconf-app/<version>/bin/{activate,python}``. Le ``manage.py`` factice note ce
qu'il reçoit ; un dernier test lance les vraies commandes ``run_jobs`` et ``cleanup`` en
réglages de production (SQLite jetable), comme le cron du serveur.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import get_commands, load_command_class

from apps.core.management.base import LockedCommand

REPO_DIR = Path(settings.BASE_DIR).parent
CRON_SCRIPT = REPO_DIR / "deploy" / "cron.sh"
BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(BASH is None, reason="bash absent")

EX_USAGE = 64
EX_CONFIG = 78

LOG_LINE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ (?P<command>[a-z_]+)\[\d+\] (?P<text>.*)$")

FAKE_MANAGE = """\
import json, os, sys
keys = ("DJANGO_SETTINGS_MODULE", "VIRTUAL_ENV", "FAKE_ACTIVATED", "GESTCONF_ENV_FILE",
        "PYTHONIOENCODING")
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "calls.jsonl"), "a") as f:
    record = {"argv": sys.argv, "cwd": os.getcwd(), "env": {k: os.environ.get(k) for k in keys}}
    f.write(json.dumps(record) + "\\n")
print("sortie standard de la commande")
print("détail confidentiel sur la sortie d'erreur", file=sys.stderr)
sys.exit(int(os.environ.get("FAKE_EXIT", "0")))
"""


@dataclass
class Server:
    """Arborescence du compte o2switch simulée sous ``home``."""

    home: Path
    data_dir: Path | None = None  # base SQLite et verrous des commandes réelles

    @property
    def app(self) -> Path:
        return self.home / "gestconf-app"

    @property
    def log(self) -> Path:
        return self.app / "logs" / "cron.log"

    @property
    def conf(self) -> Path:
        return self.app / "cron.conf"

    def make_venv(self, version: str, python: str = sys.executable) -> Path:
        """Venv « cPanel » : activate (marqué FAKE_ACTIVATED) et python (vers ``python``)."""
        root = self.home / "virtualenv" / "gestconf-app" / version
        bin_dir = root / "bin"
        bin_dir.mkdir(parents=True)
        (bin_dir / "activate").write_text(
            f'VIRTUAL_ENV="{root}"\nexport VIRTUAL_ENV\nexport FAKE_ACTIVATED="{version}"\n'
            'PATH="$VIRTUAL_ENV/bin:$PATH"\nexport PATH\n'
        )
        wrapper = bin_dir / "python"
        wrapper.write_text(f'#!/bin/sh\nexec "{python}" "$@"\n')
        wrapper.chmod(0o755)
        return bin_dir / "activate"

    def write_conf(self, text: str, mode: int = 0o600) -> None:
        self.conf.write_text(text)
        self.conf.chmod(mode)

    def run(self, *args: str, **extra_env: str) -> subprocess.CompletedProcess[str]:
        # Environnement minimal, comme celui du cron.
        env = {"HOME": str(self.home), "PATH": "/usr/bin:/bin", **extra_env}
        return subprocess.run(  # noqa: S603  # arguments maîtrisés par le test
            [BASH, str(self.app / "deploy" / "cron.sh"), *args],
            env=env,
            cwd=self.home,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def calls(self) -> list[dict]:
        path = self.app / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def log_lines(self) -> list[re.Match[str]]:
        lines = self.log.read_text().splitlines()
        matches = [LOG_LINE.match(line) for line in lines]
        assert all(matches), f"ligne de journal sans préfixe : {lines}"
        return [match for match in matches if match]


@pytest.fixture
def server(tmp_path: Path) -> Server:
    srv = Server(home=tmp_path / "home")
    (srv.app / "deploy").mkdir(parents=True)
    script = srv.app / "deploy" / "cron.sh"
    shutil.copy(CRON_SCRIPT, script)
    script.chmod(0o755)
    (srv.app / "manage.py").write_text(FAKE_MANAGE)
    (srv.app / ".env").write_text("DJANGO_SECRET_KEY=x\n")
    (srv.app / "RELEASE").write_text("abc1234\n")
    return srv


# --- Liste blanche ------------------------------------------------------------------------


def allowed_commands() -> list[str]:
    match = re.search(r"^readonly ALLOWED_COMMANDS=\(([^)]*)\)$", CRON_SCRIPT.read_text(), re.M)
    assert match, "ALLOWED_COMMANDS absent de cron.sh"
    return match.group(1).split()


def test_allowed_commands_are_locked_cron_commands():
    """Règle n° 9 : chaque commande lancée par le cron est verrouillée (LockedCommand), donc
    sans exécution concurrente, et note son battement de cœur (supervision par /health)."""
    commands = get_commands()
    assert allowed_commands() == ["run_jobs", "cleanup"]
    for name in allowed_commands():
        command = load_command_class(commands[name], name)
        assert isinstance(command, LockedCommand), name
        assert command.heartbeat_enabled, name


def test_documented_cron_lines_use_allowed_commands():
    """Les lignes de cron documentées n'appellent que des commandes de la liste blanche."""
    for doc in (REPO_DIR / "deploy" / "README.md", REPO_DIR / "README.md"):
        used = set(re.findall(r"deploy/cron\.sh (\w+)", doc.read_text(encoding="utf-8")))
        assert used, f"aucune ligne de cron dans {doc}"
        # check_integrity (L1.8) n'est citée que comme tâche à venir.
        assert used <= {*allowed_commands(), "check_integrity"}, doc


def test_cron_script_never_interprets_configuration_files():
    """Seul le script activate du venv est exécuté ; .env et cron.conf ne sont jamais
    « sourcés » ni évalués (un .env contient des secrets et des valeurs non shell)."""
    code = "\n".join(
        line for line in CRON_SCRIPT.read_text().splitlines() if not line.lstrip().startswith("#")
    )
    assert re.findall(r"^\s*(?:source|\.)\s+(.+)$", code, re.M) == ['"$GESTCONF_VENV_ACTIVATE"']
    assert not re.search(r"\beval\b", code)
    assert "export DJANGO_SETTINGS_MODULE=config.settings.prod" in code


# --- Exécution ------------------------------------------------------------------------------


def test_cron_runs_manage_py_like_passenger(server: Server):
    """Même code (dossier de l'application), même venv (activate puis son python), réglages
    de production imposés même si l'environnement en désigne d'autres ; rien sur la sortie."""
    activate = server.make_venv("3.12")
    result = server.run(
        "run_jobs", "--max-seconds", "240", DJANGO_SETTINGS_MODULE="config.settings.dev"
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    [call] = server.calls()
    assert call["argv"] == ["manage.py", "run_jobs", "--max-seconds", "240"]
    assert call["cwd"] == str(server.app)
    assert call["env"] == {
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "VIRTUAL_ENV": str(activate.parent.parent),
        "FAKE_ACTIVATED": "3.12",
        "GESTCONF_ENV_FILE": None,
        "PYTHONIOENCODING": "utf-8",
    }
    lines = server.log_lines()
    assert {line["command"] for line in lines} == {"run_jobs"}
    texts = [line["text"] for line in lines]
    assert texts[0].startswith("début : manage.py run_jobs --max-seconds 240 (version abc1234")
    assert "sortie standard de la commande" in texts
    assert "détail confidentiel sur la sortie d'erreur" in texts
    assert texts[-1].startswith("fin : code 0 en ")
    assert (server.log.stat().st_mode & 0o077) == 0


@pytest.mark.parametrize(
    "command",
    ["migrate", "flush", "shell", "dbshell", "send_test_email", "outbox", "run_jobs ", "", "-x"],
)
def test_cron_rejects_commands_outside_the_allow_list(server: Server, command: str):
    server.make_venv("3.12")
    result = server.run(command)
    assert result.returncode == EX_USAGE
    assert "non autorisée" in result.stderr
    assert server.calls() == []


def test_cron_requires_a_command(server: Server):
    server.make_venv("3.12")
    result = server.run()
    assert result.returncode == EX_USAGE
    assert "Usage" in result.stderr
    assert server.calls() == []


@pytest.mark.parametrize(
    "option",
    ["--settings=config.settings.dev", "--settings", "--sett=x", "--pythonpath=/tmp", "--py"],
)
def test_cron_refuses_to_override_the_settings(server: Server, option: str):
    """Ni --settings ni --pythonpath, ni leurs abréviations : les réglages sont imposés."""
    server.make_venv("3.12")
    result = server.run("run_jobs", option)
    assert result.returncode == EX_USAGE
    assert "option interdite" in result.stderr
    assert server.calls() == []


def test_cron_reports_a_failure_in_one_line_without_details(server: Server):
    """En échec : code de manage.py, une ligne sur la sortie d'erreur (e-mail du cron de
    cPanel) sans la sortie de la commande, qui reste dans le journal."""
    server.make_venv("3.12")
    result = server.run("cleanup", FAKE_EXIT="3")
    assert result.returncode == 3
    assert result.stdout == ""
    [line] = result.stderr.splitlines()
    assert "« cleanup » a échoué (code 3)" in line
    assert str(server.log) in line
    assert "confidentiel" not in result.stderr
    texts = [match["text"] for match in server.log_lines()]
    assert "détail confidentiel sur la sortie d'erreur" in texts
    assert texts[-1].startswith("fin : code 3 en ")


def test_cron_refuses_to_choose_between_several_venvs(server: Server):
    server.make_venv("3.12")
    activate = server.make_venv("3.13")
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert "plusieurs venvs" in result.stderr
    assert server.calls() == []

    # Venv désigné par cron.conf (écrit par deploy.sh) : plus d'ambiguïté.
    server.write_conf(f"# écrit par deploy.sh\nGESTCONF_VENV_ACTIVATE={activate}\n")
    result = server.run("run_jobs")
    assert result.returncode == 0, result.stderr
    assert server.calls()[-1]["env"]["FAKE_ACTIVATED"] == "3.13"


def test_cron_environment_overrides_cron_conf(server: Server):
    first = server.make_venv("3.12")
    second = server.make_venv("3.13")
    server.write_conf(f"GESTCONF_VENV_ACTIVATE={first}\n")
    result = server.run("run_jobs", GESTCONF_VENV_ACTIVATE=str(second))
    assert result.returncode == 0, result.stderr
    assert server.calls()[-1]["env"]["FAKE_ACTIVATED"] == "3.13"


def test_cron_without_venv_is_a_configuration_error(server: Server):
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert "aucun venv" in result.stderr
    assert "GESTCONF_VENV_ACTIVATE" in result.stderr


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o666])
def test_cron_conf_must_not_be_writable_by_others(server: Server, mode: int):
    """cron.conf désigne un script exécuté : modifiable par le seul compte."""
    activate = server.make_venv("3.12")
    server.write_conf(f"GESTCONF_VENV_ACTIVATE={activate}\n", mode=mode)
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert "chmod 600" in result.stderr
    assert server.calls() == []


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("DATABASE_URL=mysql://u:p@h/db\n", "clé inconnue DATABASE_URL"),
        ("export GESTCONF_CRON_LOG=/tmp/x.log\n", "CLÉ=valeur"),
        ("GESTCONF_CRON_LOG=logs/cron.log\n", "chemin absolu"),
        ("GESTCONF_VENV_ACTIVATE=$(touch PWNED)\n", "chemin absolu"),
        ("GESTCONF_CRON_LOG_MAX_BYTES=a[$(touch PWNED)]\n", "nombre d'octets"),
    ],
)
def test_cron_conf_is_parsed_never_executed(server: Server, content: str, message: str):
    server.make_venv("3.12")
    server.write_conf(content)
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert message in result.stderr
    assert server.calls() == []
    assert not list(server.home.parent.rglob("PWNED"))


def test_cron_requires_the_env_file_read_by_django(server: Server, tmp_path: Path):
    """Même .env que Passenger : celui que lisent les réglages (défaut ou GESTCONF_ENV_FILE)."""
    activate = server.make_venv("3.12")
    (server.app / ".env").unlink()
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert "fichier .env" in result.stderr
    assert server.calls() == []

    other = tmp_path / "secrets" / "gestconf.env"
    other.parent.mkdir()
    other.write_text("DJANGO_SECRET_KEY=x\n")
    server.write_conf(f"GESTCONF_VENV_ACTIVATE={activate}\nGESTCONF_ENV_FILE={other}\n")
    result = server.run("run_jobs")
    assert result.returncode == 0, result.stderr
    assert server.calls()[-1]["env"]["GESTCONF_ENV_FILE"] == str(other)


def test_cron_rotates_its_log(server: Server):
    activate = server.make_venv("3.12")
    # « 04000 » : lu en base 10 (4 000 octets), et non en octal par l'arithmétique de bash.
    server.write_conf(f"GESTCONF_VENV_ACTIVATE={activate}\nGESTCONF_CRON_LOG_MAX_BYTES=04000\n")
    server.log.parent.mkdir()
    old = "ancienne ligne\n" * 300  # 4 500 octets
    server.log.write_text(old)
    assert server.run("run_jobs").returncode == 0
    assert (server.log.parent / "cron.log.1").read_text() == old
    assert "ancienne ligne" not in server.log.read_text()
    size = server.log.stat().st_size
    assert size < 2000
    assert server.run("run_jobs").returncode == 0
    assert server.log.stat().st_size > size  # sous le seuil : ajout, pas de rotation


def test_cron_must_live_in_the_application_deploy_dir(server: Server):
    server.make_venv("3.12")
    (server.app / "manage.py").unlink()
    result = server.run("run_jobs")
    assert result.returncode == EX_CONFIG
    assert "manage.py absent" in result.stderr


# --- Commandes réelles en réglages de production -------------------------------------------


@pytest.fixture
def production_app(server: Server, tmp_path: Path) -> Server:
    """``manage.py`` réel (lien symbolique), réglages de production, SQLite jetable migrée."""
    (server.app / "manage.py").unlink()
    (server.app / "manage.py").symlink_to(Path(settings.BASE_DIR) / "manage.py")
    data = tmp_path / "data"
    (data / "locks").mkdir(parents=True)
    env_file = server.app / ".env"
    # BASE_DIR des réglages est le vrai dossier backend (liens résolus) : le .env factice
    # leur est désigné par GESTCONF_ENV_FILE, comme le permet cron.conf.
    env_file.write_text(
        "DJANGO_SECRET_KEY=test-only-0123456789abcdefghijklmnopqrstuvwxyz-0123456789\n"
        "DJANGO_ALLOWED_HOSTS=conference.exemple.org\n"
        "DJANGO_CSRF_TRUSTED_ORIGINS=https://conference.exemple.org\n"
        f"DATABASE_URL=sqlite:///{data / 'db.sqlite3'}\n"
        f"GESTCONF_LOCK_DIR={data / 'locks'}\n"
    )
    activate = server.make_venv("3.12")
    server.write_conf(f"GESTCONF_VENV_ACTIVATE={activate}\nGESTCONF_ENV_FILE={env_file}\n")
    env = {
        "HOME": str(server.home),
        "PATH": "/usr/bin:/bin",
        "DJANGO_SETTINGS_MODULE": "config.settings.prod",
        "GESTCONF_ENV_FILE": str(env_file),
    }
    for command in (["migrate", "--noinput"], ["createcachetable"]):
        subprocess.run(  # noqa: S603  # arguments maîtrisés par le test
            [sys.executable, "manage.py", *command],
            cwd=settings.BASE_DIR,
            env=env,
            check=True,
            capture_output=True,
            timeout=300,
        )
    server.data_dir = data
    return server


def heartbeats(server: Server) -> dict[str, tuple[str, str | None]]:
    assert server.data_dir is not None
    with sqlite3.connect(server.data_dir / "db.sqlite3") as connection:
        rows = connection.execute(
            "SELECT name, last_status, last_success_at FROM core_cronheartbeat"
        ).fetchall()
    return {name: (status, success) for name, status, success in rows}


def test_cron_runs_the_real_commands_with_production_settings(production_app: Server):
    """De bout en bout : cron.sh lance run_jobs puis cleanup en réglages de production, avec
    le .env désigné (dossier des verrous compris) ; battements de cœur réussis, donc /health
    passerait à « jobs: ok »."""
    result = production_app.run("run_jobs", "--max-seconds", "5")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    result = production_app.run("cleanup")
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")

    beats = heartbeats(production_app)
    assert beats["run_jobs"][0] == "succeeded"
    assert beats["run_jobs"][1] is not None
    assert beats["cleanup"][0] == "succeeded"
    locks = production_app.data_dir / "locks"
    assert {path.name for path in locks.iterdir()} >= {"run_jobs.lock", "cleanup.lock"}
    texts = [match["text"] for match in production_app.log_lines()]
    assert any(text.startswith("Tâches exécutées : 0") for text in texts)


def test_cron_exits_cleanly_when_the_command_lock_is_held(production_app: Server):
    """Règle n° 9 : un passage qui trouve le verrou pris sort sans erreur (code 0, rien sur
    la sortie, donc pas d'e-mail du cron) et le note dans le journal."""
    lock_path = production_app.data_dir / "locks" / "run_jobs.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = production_app.run("run_jobs", "--max-seconds", "5")
    finally:
        os.close(fd)
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")
    texts = [match["text"] for match in production_app.log_lines()]
    assert any("déjà en cours d'exécution" in text for text in texts)
    assert "run_jobs" not in heartbeats(production_app)
