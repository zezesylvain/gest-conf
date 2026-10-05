"""Garde-fous sur les scripts de déploiement (plan L1 §11, étapes L1.0 et L1.1).

Ces scripts ne sont pas du Python : on vérifie dans leur texte les invariants qui ont
déjà causé un défaut (CSP absente en production, bug L0) ou qui doivent rester alignés
sur les réglages Django (mode SQL, interclassement).
"""

import json
import re
from pathlib import Path

from django.conf import settings

from config.settings.base import database_from_env

REPO_DIR = Path(settings.BASE_DIR).parent
DEPLOY_SCRIPT = REPO_DIR / "deploy" / "deploy.sh"
CHECK_SCRIPT = REPO_DIR / "deploy" / "check-o2switch.sh"


def shell_code(path: Path) -> str:
    """Texte du script sans ses lignes de commentaire."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("#"))


def test_deploy_builds_angular_with_the_csp_script():
    """Bug L0 : « ng build » lancé directement publiait les pages sans CSP à empreintes."""
    code = shell_code(DEPLOY_SCRIPT)
    assert "npm run build" in code
    assert not re.search(r"\bng build\b", code)


def test_npm_build_injects_the_csp():
    """Second maillon : « npm run build » lance web/scripts/inject-csp.mjs après les builds."""
    package = json.loads((REPO_DIR / "web" / "package.json").read_text(encoding="utf-8"))
    build = package["scripts"]["build"]
    assert "ng build portail" in build
    assert "ng build gestion" in build
    assert build.rstrip().split("&&")[-1].strip().startswith("node scripts/inject-csp.mjs")


def test_deploy_creates_the_cache_table_after_migrate():
    """Sans table de cache, /health répond 503 et toute vue limitée en débit échoue."""
    code = shell_code(DEPLOY_SCRIPT)
    assert code.index("manage.py migrate") < code.index("manage.py createcachetable")


def test_deploy_installs_locked_dependencies_with_hashes():
    code = shell_code(DEPLOY_SCRIPT)
    assert re.search(r"pip install [^\n]*--require-hashes[^\n]*-r requirements/prod\.txt", code)


def test_o2switch_check_expects_the_application_sql_mode():
    """L1.0 (R19) : le script vérifie que MariaDB accepte le mode imposé par l'application."""
    expected = f"readonly EXPECTED_SQL_MODE='{settings.MARIADB_SQL_MODE}'"
    assert expected in CHECK_SCRIPT.read_text(encoding="utf-8")


def test_o2switch_check_expects_the_test_database_collation(monkeypatch):
    """Interclassement exigé en production = celui de la base de test MariaDB."""
    monkeypatch.setenv("DATABASE_URL", "mysql://user:password@localhost:3306/gestconf")
    collation = database_from_env()["TEST"]["COLLATION"]
    expected = f"readonly EXPECTED_COLLATION='{collation}'"
    assert expected in CHECK_SCRIPT.read_text(encoding="utf-8")


def test_deploy_runs_checks_before_migrate_with_database_checks():
    """Un avertissement arrête le déploiement avant toute migration (DDL non transactionnel
    sous MariaDB). Sécurité sans --database (sinon models.W036 des contraintes
    conditionnelles d'allauth, plan L1 §3.7) ; base seule par --tag database (mysql.W002)."""
    code = shell_code(DEPLOY_SCRIPT)
    security = "manage.py check --deploy --fail-level WARNING"
    database = "manage.py check --database default --tag database --fail-level WARNING"
    assert security in code
    assert database in code
    assert "check --deploy --database" not in code
    migrate = code.index("manage.py migrate")
    assert code.index("pip install") < code.index(security) < migrate
    assert code.index("pip install") < code.index(database) < migrate


def test_deploy_ships_only_committed_backend_files():
    """git archive du commit déployé : aucun fichier ignoré du poste (.coverage, htmlcov/,
    .env.local...) n'est envoyé sur le serveur."""
    code = shell_code(DEPLOY_SCRIPT)
    assert re.search(r'git -C "\$ROOT" archive [^\n]*"\$RELEASE" backend', code)
    assert '"$STAGING/backend/" "$DEPLOY_SSH:$DEPLOY_APP_DIR/"' in code
    assert '"$ROOT/backend/"' not in code


def test_deploy_checks_the_csp_of_every_built_page():
    """Toutes les pages HTML du build (pré-rendues comprises), pas une liste fixe."""
    code = shell_code(DEPLOY_SCRIPT)
    assert re.search(r"find \"\$ROOT/web/dist\" -name '\*\.html'", code)
    assert "grep -L 'http-equiv=\"Content-Security-Policy\"'" in code


def test_smoke_test_checks_that_diagnostics_are_disabled():
    """M09 automatisé : un GESTCONF_DIAGNOSTICS=1 oublié fait échouer le test de fumée."""
    code = shell_code(REPO_DIR / "deploy" / "smoke-test.sh")
    assert '"$BASE_URL/api/v1/diagnostics/request")" == "404"' in code


def _locked_requirement(name: str) -> tuple[str, set[str]]:
    """(« nom==version », empreintes) d'un paquet de requirements/prod.txt."""
    text = (Path(settings.BASE_DIR) / "requirements" / "prod.txt").read_text(encoding="utf-8")
    match = re.search(
        rf"^({re.escape(name)}==\S+) \\\n((?:\s+--hash=sha256:\w+(?: \\)?\n)+)", text, re.M
    )
    assert match, f"{name} absent de prod.txt"
    return match.group(1), set(re.findall(r"sha256:(\w+)", match.group(2)))


def test_o2switch_check_installs_the_locked_pymysql():
    """Les contrôles MariaDB manipulent le mot de passe de production : PyMySQL y est
    installé avec la version et les empreintes de prod.txt, jamais « pip install PyMySQL »."""
    pin, hashes = _locked_requirement("pymysql")
    line = re.search(r"^readonly PYMYSQL_REQUIREMENT='([^']+)'", CHECK_SCRIPT.read_text(), re.M)
    assert line, "PYMYSQL_REQUIREMENT absent du script"
    assert line.group(1).split()[0] == pin
    assert set(re.findall(r"sha256:(\w+)", line.group(1))) == hashes
    code = shell_code(CHECK_SCRIPT)
    assert "--require-hashes" in code
    assert "--no-deps" in code
    assert not re.search(r"pip install [^\n]* PyMySQL\b", code)


def test_o2switch_check_pins_crypto_versions():
    """V03 essaie les versions prévues pour L1.3 et L1.6, pas la dernière publiée."""
    line = re.search(r"^readonly CRYPTO_REQUIREMENTS=\(([^)]+)\)", CHECK_SCRIPT.read_text(), re.M)
    assert line
    assert all("==" in requirement for requirement in line.group(1).split())


def test_o2switch_check_pins_pillow_version():
    """V28 (lot L2, E4) : la version de Pillow essayée est épinglée et le réencodage testé."""
    code = CHECK_SCRIPT.read_text(encoding="utf-8")
    line = re.search(r"^readonly PILLOW_REQUIREMENT='([^']+)'", code, re.M)
    assert line and "==" in line.group(1)
    assert "report V28 OK" in code
    assert 'assert not reread.getexif(), "EXIF conservé"' in code


def test_o2switch_check_controls_innodb_row_format():
    """V27 : sans DYNAMIC (ou pages < 8 Kio), migrate échoue sur les index utf8mb4 longs."""
    code = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert "@@innodb_default_row_format" in code
    assert "@@innodb_page_size" in code


# --- Commandes planifiées (étape L1.2, plan §8.4) ----------------------------------------

CRON_SCRIPT = REPO_DIR / "deploy" / "cron.sh"


def test_deploy_ships_the_cron_script_from_the_commit():
    """deploy/cron.sh est extrait du commit déployé, comme le code Django, et le chemin du
    venv de Passenger est écrit pour lui (VENV_ACTIVATE), puis protégé du rsync --delete."""
    code = shell_code(DEPLOY_SCRIPT)
    assert 'git -C "$ROOT" show "$RELEASE:deploy/cron.sh"' in code
    assert "> VENV_ACTIVATE" in code
    assert "--exclude '/VENV_ACTIVATE'" in code
    assert "--exclude '/logs/'" in code


def test_cron_script_only_runs_scheduled_commands():
    """Liste fermée : le script cron n'est pas un accès générique à manage.py."""
    code = shell_code(CRON_SCRIPT)
    assert re.search(r"^\s*run_jobs \| cleanup \| check_integrity\)", code, re.M)
    assert "config.settings.prod" in code
    assert CRON_SCRIPT.stat().st_mode & 0o111


def test_smoke_test_checks_the_job_queue():
    code = shell_code(REPO_DIR / "deploy" / "smoke-test.sh")
    assert 'json_has "$health" jobs \'"ok"\'' in code


def test_smoke_test_checks_the_allauth_bootstrap():
    """Étape L1.3 (plan §11) : amorçage anonyme 401 JSON et cookie CSRF posé."""
    code = shell_code(REPO_DIR / "deploy" / "smoke-test.sh")
    assert '"$BASE_URL/api/_allauth/browser/v1/auth/session"' in code
    assert "set-cookie 'csrftoken='" in code


def test_smoke_test_checks_the_public_current_edition():
    """Étape L1.5 (plan §11) : édition publique courante, 200 ou 404 JSON."""
    code = shell_code(REPO_DIR / "deploy" / "smoke-test.sh")
    assert '"$BASE_URL/api/v1/public/editions/current"' in code
