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
    """Second maillon : « npm run build » lance web/scripts/inject-csp.mjs après les builds.

    Seules suivent les étapes du service worker de l'accueil (plan L7, K5), qui ne
    modifient aucune page : régénérer ``ngsw.json``, dont les empreintes couvrent
    ``index.html`` réécrit par la CSP, puis les contrôler."""
    package = json.loads((REPO_DIR / "web" / "package.json").read_text(encoding="utf-8"))
    steps = [step.strip() for step in package["scripts"]["build"].split("&&")]
    csp = next(i for i, step in enumerate(steps) if step.startswith("node scripts/inject-csp.mjs"))
    assert any(step.startswith("ng build portail") for step in steps[:csp])
    assert any(step.startswith("ng build gestion") for step in steps[:csp])
    after = steps[csp + 1 :]
    assert [step.split()[0:2] for step in after] == [
        ["ngsw-config", "dist/gestion/browser"],
        ["node", "scripts/check-ngsw.mjs"],
    ]


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
    # Même version que le fichier verrouillé : V28 vérifie ce que deploy.sh installera.
    locked = (REPO_DIR / "backend" / "requirements" / "base.txt").read_text(encoding="utf-8")
    assert re.search(rf"^{re.escape(line.group(1).lower())} \\$", locked, re.M)
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
    scheduled = (
        r"^\s*run_jobs \| close_call \| remind_drafts \| remind_reviewers \| "
        r"remind_presentations \| cleanup \| \\\n\s*check_integrity \| "
        r"expire_registrations \| sync_payments \| remind_tasks \| backup_db\)"
    )
    assert re.search(scheduled, code, re.M)
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


def test_npm_build_portail_checks_the_prerender_then_injects_the_csp():
    """E9 (plan L2) : la republication du portail contrôle la complétude puis pose la CSP."""
    package = json.loads((REPO_DIR / "web" / "package.json").read_text(encoding="utf-8"))
    for name in ("build", "build:portail"):
        steps = [step.strip() for step in package["scripts"][name].split("&&")]
        check = steps.index("node scripts/check-prerender.mjs dist/portail/browser")
        assert steps[check - 1] == "ng build portail"
        csp = next(i for i, step in enumerate(steps) if step.startswith("node scripts/inject-csp"))
        assert steps[csp].startswith("node scripts/inject-csp.mjs dist/portail/browser")
        # Après la CSP, plus aucune page n'est réécrite : seules suivent, dans « build », les
        # étapes du service worker de la gestion (plan L7).
        assert all("portail" not in step for step in steps[csp + 1 :])
    assert (
        package["scripts"]["build:portail"]
        .split("&&")[-1]
        .strip()
        .startswith("node scripts/inject-csp.mjs")
    )


def test_portal_only_publication_spares_gestion_and_api_then_marks_published():
    """E9 : --portal-only ne touche ni /gestion/ ni /api/, puis enregistre la mise en ligne
    datée du début du build (une modification faite pendant le build reste à publier)."""
    code = shell_code(DEPLOY_SCRIPT)
    function = code[
        code.index("publish_portal() {") : code.index("\n}\n", code.index("publish_portal() {"))
    ]
    assert "npm run build:portail" in function
    assert 'GESTCONF_PRERENDER_API_ORIGIN="$origin"' in function
    rsync = function[function.index("rsync -az --delete") :]
    assert "--exclude '/gestion/'" in rsync and "--exclude '/api/'" in rsync
    assert "--exclude '/.htaccess'" in rsync
    assert function.index("rsync -az --delete") < function.index("mark_portal_published")
    assert '--built-at "$built_at"' in function
    assert function.index("built_at=") < function.index("npm run build:portail")
    # Déploiement complet : portail publié après la mise en ligne du backend.
    assert code.index("touch tmp/restart.txt") < code.rindex("publish_portal\n")


def test_smoke_test_checks_the_prerendered_portal_and_public_files():
    """L2.6 : pages pré-rendues, canonique, plan du site, fichier public."""
    code = shell_code(REPO_DIR / "deploy" / "smoke-test.sh")
    assert '"$BASE_URL/sitemap.xml"' in code
    assert 'data-gc-rendered="en:call"' in code
    assert "/api/v1/public/files/00000000-0000-0000-0000-000000000000/x.pdf" in code


PULL_SCRIPT = REPO_DIR / "deploy" / "pull-backups.sh"
RESTORE_SCRIPT = REPO_DIR / "deploy" / "restore.sh"


def test_deploy_backs_up_before_migrating():
    """Plan L9, S3 : sauvegarde fraîche avant migrate, obligatoire (--required)."""
    code = shell_code(DEPLOY_SCRIPT)
    backup = code.index("python manage.py backup_db --required")
    assert backup < code.index("python manage.py migrate --noinput")
    assert code.index("check --database default") < backup


def test_deploy_never_deletes_uploaded_files_nor_backups():
    """var/ (fichiers déposés et sauvegardes par défaut) est ignoré par git : sans exclusion,
    le rsync --delete du déploiement l'effacerait (défaut trouvé en L9.1)."""
    code = shell_code(DEPLOY_SCRIPT)
    assert "--exclude '/var/'" in code
    gitignore = (REPO_DIR / ".gitignore").read_text(encoding="utf-8")
    assert "backend/var/" in gitignore
    assert 'show "$RELEASE:deploy/restore.sh"' in code


def test_pull_backups_keeps_dated_snapshots_and_verifies_the_copy():
    """Copie hors hébergement tirée par l'opérateur : jamais de --delete (un effacement sur
    le serveur ne gagne pas la copie), instantanés liés (--link-dest), empreinte vérifiée."""
    code = shell_code(PULL_SCRIPT)
    assert "--delete" not in code
    assert "--link-dest=" in code
    assert 'mv "$partial" "$snapshot"' in code
    assert 'ln -sfn "$stamp" "$PULL_DEST/files/latest"' in code
    assert "hashlib.sha256()" in code and 'manifest["database"]["sha256"]' in code
    assert "umask 077" in code
    # Installation neuve : dossier distant des fichiers absent, instantané vide (L9.7).
    assert "test -d '$remote'" in code and 'mkdir -p "$partial/$name"' in code
    assert PULL_SCRIPT.stat().st_mode & 0o111


def test_restore_script_restores_then_checks_integrity():
    code = shell_code(RESTORE_SCRIPT)
    assert code.index("manage.py restore_db") < code.index("manage.py check_integrity")
    assert "--files-from" in code
    # check_integrity rend 0 avec des anomalies : le script les cherche dans la sortie (L9.7).
    assert "'-> [1-9][0-9]* anomalie'" in code
    assert RESTORE_SCRIPT.stat().st_mode & 0o111


SMOKE_SCRIPT = REPO_DIR / "deploy" / "smoke-test.sh"
PORTAL_HTACCESS = REPO_DIR / "deploy" / "apache" / "public_html.htaccess"


def test_smoke_test_checks_security_headers_and_https_redirect():
    """Plan L9, S7 : les en-têtes du .htaccess sont dans <IfModule mod_headers.c> et
    disparaîtraient sans bruit si le module manquait ; la redirection HTTPS (cPanel) aussi."""
    code = shell_code(SMOKE_SCRIPT)
    for header in ("x-content-type-options", "x-frame-options", "referrer-policy"):
        assert f'has_header "$headers" {header}' in code
    assert "strict-transport-security 'max-age=[1-9]'" in code
    assert '"http://${BASE_URL#https://}/fr/"' in code
    assert "(301|308)" in code
    assert 'json_has "$health" backup \'"ok"\'' in code


def test_portal_csp_header_lists_every_fetch_directive_but_scripts():
    """Plan L9, bilan de L9.0 : pas de default-src dans l'en-tête, qui s'appliquerait aux
    scripts et bloquerait les scripts en ligne autorisés par la CSP à empreintes de chaque
    page (<meta>) ; chaque autre directive de chargement y est donc explicite."""
    text = PORTAL_HTACCESS.read_text(encoding="utf-8")
    policy = re.search(r'Content-Security-Policy "([^"]+)"', text).group(1)
    directives = {part.split()[0] for part in policy.split(";") if part.strip()}
    assert "default-src" not in directives and "script-src" not in directives
    fetch = {
        "object-src",
        "frame-src",
        "img-src",
        "font-src",
        "style-src",
        "connect-src",
        "media-src",
        "manifest-src",
        "worker-src",
    }
    assert fetch <= directives
    assert {"base-uri", "form-action", "frame-ancestors"} <= directives
    assert "frame-ancestors 'none'" in policy and "object-src 'none'" in policy


def test_scripts_run_on_the_host_avoid_process_substitution():
    """Relevé du 17 octobre 2026 : « < <(…) » échoue sur l'hébergement (/dev/fd absent sous
    CageFS) ; les scripts exécutés sur o2switch passent par des fichiers temporaires."""
    for script in ("check-o2switch.sh", "cron.sh", "restore.sh"):
        code = shell_code(REPO_DIR / "deploy" / script)
        assert "<(" not in code, script
