#!/usr/bin/env bash
# Vérifications de l'hébergement o2switch, étape L1.0 (plan L1 §13 et §14.2).
#
# Script en LECTURE SEULE, à lancer en SSH dans le compte o2switch. Résultats à reporter
# dans docs/L1-verifications-o2switch.md (identifiants V00 à V27).
#
#   # Sans copier le script sur le serveur (sortie enregistrée sur le poste local) :
#   ssh compte@serveur 'bash -s' < deploy/check-o2switch.sh | tee check-o2switch.txt
#   ssh compte@serveur 'bash -s -- --app-dir ~/gestconf-app' < deploy/check-o2switch.sh
#
# Options :
#   --app-dir DIR     dossier de l'application Django (défaut : ~/gestconf-app)
#   --env-file FILE   fichier .env de production (défaut : <app-dir>/.env)
#   --public-dir DIR  racine web (défaut : ~/public_html)
#   --no-network      ni téléchargement (venv jetable) ni accès HTTPS sortant
#
# Garanties :
#   - écritures limitées à un dossier temporaire créé par mktemp dans $HOME (venv jetable,
#     programmes de contrôle) et à un fichier de verrou temporaire dans <app-dir>/tmp/,
#     supprimés à la sortie ; pip sans cache (--no-cache-dir) ; aucun .pyc écrit ailleurs ;
#   - aucun secret affiché : le .env est lu par un programme Python qui n'en affiche
#     aucune valeur (ni DATABASE_URL, ni mot de passe, ni DJANGO_SECRET_KEY) ; les erreurs
#     MariaDB sont réduites à leur code ; les valeurs des SetEnv des .htaccess sont masquées ;
#     la sortie de « manage.py check » est filtrée.
# Chaque contrôle affiche OK, ÉCHEC ou INFO ; un récapitulatif termine la sortie.
# Code de sortie : 1 si au moins un ÉCHEC, 0 sinon.

set -uo pipefail
shopt -s nullglob

# Doit rester identique à MARIADB_SQL_MODE (backend/config/settings/base.py) : vérifié par
# backend/tests/test_deploy_scripts.py.
readonly EXPECTED_SQL_MODE='STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'
# Interclassement attendu, identique à celui de la base de test (DATABASES["TEST"]).
readonly EXPECTED_COLLATION='utf8mb4_unicode_ci'
# PyMySQL des contrôles MariaDB, qui manipulent DATABASE_URL (donc le mot de passe de
# production) : version ET empreintes identiques à backend/requirements/prod.txt (vérifié
# par backend/tests/test_deploy_scripts.py), installée avec --require-hashes --no-deps dans
# un venv qui ne contient rien d'autre. Seulement si le venv de l'application n'a pas déjà
# PyMySQL (installé par deploy.sh depuis prod.txt, empreintes vérifiées), préféré.
readonly PYMYSQL_REQUIREMENT='pymysql==1.2.3 --hash=sha256:14f1c68e2ed859243ae5ca41ffbe677027fc46bc136a9f0be8a4e928e5e7415a --hash=sha256:d5b288529782e536ae171866df3ca9dc4f6cbfb3cc2f18e6f837fbb90dbc262b'
# V03 : versions prévues pour L1.3 et L1.6 (cryptography revérifiée par le plan L1 ;
# fido2 : dernière version compatible avec l'extra « mfa » d'allauth 65.19.7, <3), et non
# la dernière publiée. Venv séparé de celui des contrôles MariaDB : ces paquets (et leurs
# dépendances, non épinglées) ne s'exécutent jamais à côté des identifiants de la base.
readonly CRYPTO_REQUIREMENTS=(cryptography==50.0.2 fido2==2.2.1)

APP_DIR="$HOME/gestconf-app"
ENV_FILE=""
PUBLIC_DIR="$HOME/public_html"
NETWORK=1

SUMMARY=()
COUNT_OK=0
COUNT_FAIL=0
COUNT_INFO=0
WORK=""
LOCK_FILE=""

usage() { sed -n '2,/^$/s/^# \{0,1\}//p' "$0" 2>/dev/null || echo "Voir l'en-tête du script."; }

# shellcheck disable=SC2317  # appelée par « trap … EXIT »
cleanup() {
  if [[ -n "$LOCK_FILE" ]]; then rm -f -- "$LOCK_FILE"; fi
  if [[ -n "$WORK" ]]; then rm -rf -- "$WORK"; fi
}

# report <ID> <OK|ÉCHEC|INFO> <libellé> [détail]
report() {
  local line="$1  [$2]  $3"
  if [[ -n "${4:-}" ]]; then line+=" : $4"; fi
  printf '  %s\n' "$line"
  SUMMARY+=("$line")
  case "$2" in
    OK) COUNT_OK=$((COUNT_OK + 1)) ;;
    ÉCHEC) COUNT_FAIL=$((COUNT_FAIL + 1)) ;;
    *) COUNT_INFO=$((COUNT_INFO + 1)) ;;
  esac
}

section() { printf '\n== %s\n' "$*"; }

# join_by <séparateur> <élément>... : éléments séparés par une chaîne (et non un caractère).
join_by() {
  local separator="$1" result="" item
  shift
  for item in "$@"; do result+="${result:+$separator}$item"; done
  printf '%s' "$result"
}

# filesystem <chemin> : type de système de fichiers et option noexec éventuelle.
filesystem() {
  local fstype options
  fstype="$(findmnt -n -o FSTYPE --target "$1" 2>/dev/null || stat -f -c %T "$1" 2>/dev/null)"
  options="$(findmnt -n -o OPTIONS --target "$1" 2>/dev/null)"
  printf '%s' "${fstype:-inconnu}"
  if [[ ",$options," == *,noexec,* ]]; then printf ' (NOEXEC)'; fi
}

# version_ge A B : vrai si la version A >= B.
version_ge() { [[ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | sed -n 1p)" == "$2" ]]; }

with_timeout() {
  if command -v timeout >/dev/null; then
    timeout "$@"
  else
    shift
    "$@"
  fi
}

python_version() { "$1" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])' 2>/dev/null; }

# Interpréteurs Python visibles : Python de CloudLinux (« Setup Python App »), puis PATH.
list_pythons() {
  local -A seen=()
  local candidate real
  for candidate in /opt/alt/python3*/bin/python3 /usr/local/bin/python3.* /usr/bin/python3.* \
    /usr/bin/python3 "$(command -v python3.13)" "$(command -v python3.12)" "$(command -v python3)"; do
    [[ -n "$candidate" && -f "$candidate" && -x "$candidate" ]] || continue
    [[ "$candidate" == *-config ]] && continue
    real="$(readlink -f -- "$candidate")"
    [[ -n "${seen[$real]:-}" ]] && continue
    seen[$real]=1
    printf '%s\n' "$candidate"
  done
}

# Script « activate » du venv créé par cPanel pour l'application (convention CloudLinux :
# ~/virtualenv/<racine de l'application>/<version>/bin/activate). Version la plus élevée si plusieurs.
app_venv_activate() {
  local relative="${APP_DIR#"$HOME"/}"
  local found=("$HOME/virtualenv/$relative"/*/bin/activate)
  if ((${#found[@]} > 0)); then
    printf '%s\n' "${found[@]}" | sort -V | sed -n '$p'
  fi
}

write_helpers() {
  # Contrôles MariaDB : lecture seule ; aucune valeur du .env n'est affichée.
  cat >"$WORK/db_checks.py" <<'PY'
"""Contrôles MariaDB de check-o2switch.sh. N'affiche aucune valeur du .env."""

import re
import secrets
import sys
from urllib.parse import parse_qs, unquote, unquote_plus, urlsplit

CURRENT = ["V05"]
HINTS = {
    1040: "trop de connexions",
    1044: "accès refusé à la base",
    1045: "accès refusé (identifiant ou mot de passe)",
    1049: "base inconnue",
    1226: "limite de ressources du compte atteinte",
    1227: "privilège insuffisant",
    2003: "serveur injoignable (hôte ou port)",
    2005: "hôte inconnu",
}


def emit(check_id, status, label, detail=""):
    CURRENT[0] = check_id
    print("\t".join([check_id, status, label, " ".join(str(detail).split())]), flush=True)


def describe(error):
    code = error.args[0] if error.args and isinstance(error.args[0], int) else None
    if code is None:
        return f"erreur {type(error).__name__}"
    return f"erreur MariaDB {code} ({HINTS.get(code, 'voir la documentation MariaDB')})"


def read_env_value(path, key):
    """Même syntaxe que django-environ (Env.read_env) ; la dernière occurrence l'emporte."""
    value = None
    with open(path, encoding="utf8") as handle:
        for line in handle.read().splitlines():
            match = re.match(r"\A(?:export )?([A-Za-z_0-9]+)=(.*)\Z", line)
            if not match or match.group(1) != key:
                continue
            raw = match.group(2)
            single = re.match(r"\A'(.*)'\Z", raw)
            if single:
                raw = single.group(1)
            double = re.match(r'\A"(.*)"\Z', raw)
            if double:
                raw = re.sub(
                    r"\\(.)",
                    lambda m: "\\" + m.group(1) if m.group(1) in "rnt" else m.group(1),
                    double.group(1),
                )
            value = raw
    return value


def connection_params(url):
    """Paramètres PyMySQL, décodés comme le fait django-environ (Env.db_url_config)."""
    parts = urlsplit(url)
    if parts.scheme not in ("mysql", "mysql2"):
        raise ValueError("schéma")
    params = {
        "host": parts.hostname or "localhost",
        "port": parts.port or 3306,
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": unquote_plus(parts.path[1:].split("?", 2)[0]),
        "charset": "utf8mb4",
        "connect_timeout": 10,
        "read_timeout": 30,
        "write_timeout": 30,
    }
    socket = parse_qs(parts.query).get("unix_socket")
    if socket:
        params["unix_socket"] = socket[0]
    return params


def scalar(connection, sql, args=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()[0]


def row(connection, sql, args=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchone()


def rows(connection, sql, args=None):
    with connection.cursor() as cursor:
        cursor.execute(sql, args)
        return cursor.fetchall()


def server_checks(connection):
    version = scalar(connection, "SELECT VERSION()")
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    numbers = tuple(int(part) for part in match.groups()) if match else (0, 0, 0)
    is_mariadb = "mariadb" in version.lower()
    if is_mariadb and numbers >= (10, 5, 0):
        emit("V06", "OK", "Version de MariaDB >= 10.5 (Django 5.2)", version)
    else:
        reason = "version < 10.5" if is_mariadb else "serveur MySQL, et non MariaDB"
        emit("V06", "ÉCHEC", "Version de MariaDB >= 10.5 (Django 5.2)", f"{version} : {reason}")
    if is_mariadb and numbers >= (10, 6, 0):
        emit("V07", "INFO", "SKIP LOCKED (MariaDB >= 10.6)", "disponible")
    else:
        emit(
            "V07", "INFO", "SKIP LOCKED (MariaDB >= 10.6)",
            "indisponible ; sans effet : la file Job ne l'utilise pas (plan §8.2)",
        )

    global_mode, session_mode = row(connection, "SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode")
    strict = {"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"} & set(global_mode.split(","))
    emit(
        "V08", "INFO", "sql_mode du serveur (global)",
        f"{global_mode or '(vide)'} ; {'strict' if strict else 'NON strict'} ; sans effet sur "
        "l'application à partir de L1.1, qui impose son mode à chaque connexion (V09)",
    )

    server_charset, server_collation = row(
        connection, "SELECT @@character_set_server, @@collation_server"
    )
    database_charset, database_collation = row(
        connection,
        "SELECT DEFAULT_CHARACTER_SET_NAME, DEFAULT_COLLATION_NAME "
        "FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = DATABASE()",
    )
    table_collations = rows(
        connection,
        "SELECT IFNULL(TABLE_COLLATION, '?'), COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
        "GROUP BY TABLE_COLLATION ORDER BY TABLE_COLLATION",
    )
    tables_text = ", ".join(f"{name} x{count}" for name, count in table_collations) or "aucune"
    expected = sys.argv[3]
    good = (
        database_charset == "utf8mb4"
        and database_collation == expected
        and all(name == expected for name, _ in table_collations)
    )
    emit(
        "V10", "OK" if good else "ÉCHEC", f"Jeu de caractères utf8mb4 et interclassement {expected}",
        f"serveur {server_charset}/{server_collation} ; base {database_charset}/"
        f"{database_collation} ; tables : {tables_text}",
    )

    default_engine = scalar(connection, "SELECT @@default_storage_engine")
    engines = rows(
        connection,
        "SELECT IFNULL(ENGINE, '?'), COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' "
        "GROUP BY ENGINE ORDER BY ENGINE",
    )
    engines_text = ", ".join(f"{name} x{count}" for name, count in engines) or "aucune"
    good = default_engine == "InnoDB" and all(name == "InnoDB" for name, _ in engines)
    emit(
        "V11", "OK" if good else "ÉCHEC", "Moteur InnoDB (par défaut et tables existantes)",
        f"défaut {default_engine} ; tables : {engines_text}",
    )

    # Index utf8mb4 longs : clé primaire varchar(255) de la table de cache (1020 octets),
    # unicité (app_label, model) de django_content_type (800 octets). Plafond de 3072 octets
    # en DYNAMIC ou COMPRESSED avec des pages de 16 Kio (1536 avec 8 Kio), mais 767 octets en
    # COMPACT ou REDUNDANT, et 768 avec des pages de 4 Kio : migrate échouerait alors
    # (erreur 1709 « Index column size too large »), puis createcachetable.
    row_format, page_size = row(
        connection, "SELECT @@innodb_default_row_format, @@innodb_page_size"
    )
    formats = rows(
        connection,
        "SELECT IFNULL(ROW_FORMAT, '?'), COUNT(*) FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_TYPE = 'BASE TABLE' AND ENGINE = 'InnoDB' "
        "GROUP BY ROW_FORMAT ORDER BY ROW_FORMAT",
    )
    formats_text = ", ".join(f"{name} x{count}" for name, count in formats) or "aucune"
    long_index_formats = {"dynamic", "compressed"}
    problems = []
    if str(row_format).lower() not in long_index_formats:
        problems.append(f"format par défaut {row_format} (index limités à 767 octets)")
    if int(page_size) < 8192:
        problems.append(f"pages de {int(page_size)} octets (index limités à 768 octets)")
    if any(str(name).lower() not in long_index_formats for name, _ in formats):
        problems.append("tables existantes hors DYNAMIC/COMPRESSED")
    emit(
        "V27", "ÉCHEC" if problems else "OK",
        "Format de ligne InnoDB DYNAMIC (index utf8mb4 de 1020 octets)",
        f"défaut {row_format} ; page {int(page_size) // 1024} Kio ; tables : {formats_text}"
        + (f" ; {' ; '.join(problems)}" if problems else ""),
    )

    limits = row(
        connection,
        "SELECT @@max_user_connections, @@max_connections, @@wait_timeout, @@max_allowed_packet",
    )
    emit(
        "V13", "INFO", "Limites MariaDB",
        f"max_user_connections={limits[0]} (0 : pas de limite par compte) ; "
        f"max_connections={limits[1]} ; wait_timeout={limits[2]} s ; "
        f"max_allowed_packet={int(limits[3]) // 1024} Kio",
    )

    converted = scalar(connection, "SELECT CONVERT_TZ('2026-01-01 12:00:00', 'UTC', 'Europe/Paris')")
    emit(
        "V14", "INFO", "Tables de fuseaux horaires (CONVERT_TZ)",
        "présentes" if converted is not None
        else "absentes ; sans effet : CONVERT_TZ n'est pas utilisé (dates en UTC)",
    )


def strict_mode_check(pymysql, params, expected_mode):
    with pymysql.connect(**params, init_command=f"SET SESSION sql_mode='{expected_mode}'") as conn:
        session_mode = scalar(conn, "SELECT @@SESSION.sql_mode")
    emit(
        "V09", "OK" if session_mode == expected_mode else "ÉCHEC",
        "Mode SQL imposé par connexion (init_command de l'application)",
        f"mode de session obtenu : {session_mode}",
    )


def lock_check(pymysql, params):
    name = "gestconf.check." + secrets.token_hex(8)
    with pymysql.connect(**params) as first, pymysql.connect(**params) as second:
        steps = (
            scalar(first, "SELECT GET_LOCK(%s, 0)", (name,)),
            scalar(second, "SELECT GET_LOCK(%s, 0)", (name,)),
            scalar(first, "SELECT RELEASE_LOCK(%s)", (name,)),
            scalar(second, "SELECT GET_LOCK(%s, 0)", (name,)),
        )
        scalar(second, "SELECT RELEASE_LOCK(%s)", (name,))
    good = steps == (1, 0, 1, 1)
    emit(
        "V12", "OK" if good else "ÉCHEC", "GET_LOCK / RELEASE_LOCK exclusifs entre deux connexions",
        "pris, refusé à la 2e connexion, libéré, repris" if good
        else f"résultats inattendus {steps} (attendu (1, 0, 1, 1))",
    )


def main():
    env_file, expected_mode = sys.argv[1], sys.argv[2]
    try:
        url = read_env_value(env_file, "DATABASE_URL")
    except (OSError, UnicodeDecodeError):
        emit("V05", "ÉCHEC", "Connexion à MariaDB", "fichier .env illisible")
        return
    if not url:
        emit("V05", "ÉCHEC", "Connexion à MariaDB", "DATABASE_URL absente du fichier .env")
        return
    try:
        params = connection_params(url)
    except Exception:
        emit(
            "V05", "ÉCHEC", "Connexion à MariaDB",
            "DATABASE_URL illisible (attendu : mysql://utilisateur:motdepasse@hôte:port/base, "
            "caractères spéciaux encodés)",
        )
        return
    import pymysql

    where = params.get("unix_socket") or f"{params['host']}:{params['port']}"
    try:
        with pymysql.connect(**params) as connection:
            emit("V05", "OK", "Connexion à MariaDB (identifiants du .env, PyMySQL)", where)
            server_checks(connection)
        strict_mode_check(pymysql, params, expected_mode)
        lock_check(pymysql, params)
    except pymysql.err.MySQLError as error:
        label = "Connexion à MariaDB" if CURRENT[0] == "V05" else "Contrôles MariaDB interrompus"
        emit(CURRENT[0], "ÉCHEC", label, f"{where} : {describe(error)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # jamais de trace : elle pourrait contenir une valeur du .env
        emit(CURRENT[0], "ÉCHEC", "Contrôles MariaDB interrompus", f"erreur {type(error).__name__}")
PY

  # Verrou fcntl.flock (celui de LockedCommand, plan §8.2) : exclusif entre deux processus ?
  cat >"$WORK/flock_check.py" <<'PY'
"""Contrôle flock de check-o2switch.sh : affiche « busy acquired » si le verrou est fiable."""

import fcntl
import subprocess
import sys

CHILD = (
    "import fcntl, sys\n"
    "handle = open(sys.argv[1], 'a')\n"
    "try:\n"
    "    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
    "except BlockingIOError:\n"
    "    print('busy')\n"
    "else:\n"
    "    print('acquired')\n"
)


def child_state(path):
    result = subprocess.run(
        [sys.executable, "-c", CHILD, path], capture_output=True, text=True, timeout=30, check=False
    )
    return result.stdout.strip() or f"erreur-{result.returncode}"


path = sys.argv[1]
with open(path, "a") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    while_held = child_state(path)
print(while_held, child_state(path))
PY
}

# https_check <ID> <libellé> <URL>... : toute réponse HTTP prouve que DNS, connexion et TLS
# fonctionnent (401 attendu sans clé d'API).
https_check() {
  local check_id="$1" label="$2" url code rc details=() failed=0
  shift 2
  for url in "$@"; do
    code="$(curl --silent --show-error --output /dev/null --max-time 15 --write-out '%{http_code}' \
      "$url" 2>"$WORK/curl.err")"
    rc=$?
    if ((rc == 0)); then
      details+=("${url#https://} -> HTTP $code")
    else
      details+=("${url#https://} -> curl code $rc ($(sed -n 1p "$WORK/curl.err"))")
      failed=1
    fi
  done
  if ((failed)); then
    report "$check_id" ÉCHEC "$label" "$(join_by ' ; ' "${details[@]}")"
  else
    report "$check_id" OK "$label" "$(join_by ' ; ' "${details[@]}")"
  fi
}

# Directives Passenger d'un .htaccess (valeurs de SetEnv masquées : cPanel y écrit les
# variables d'environnement saisies dans « Setup Python App »).
htaccess_summary() {
  local file="$1"
  local passenger setenv ours
  # Valeur masquée aussi pour toute directive Passenger*Env* (variables d'environnement).
  passenger="$(grep -nE '^[[:space:]]*Passenger[A-Za-z]+' "$file" \
    | sed -E -e 's/^([0-9]+:[[:space:]]*Passenger[A-Za-z]*Env[A-Za-z]*)[[:space:]].*/\1 (valeur masquée)/' \
      -e 's/[[:space:]]+/ /g' | paste -sd '|' - | sed 's/|/ ; /g')"
  setenv="$(grep -E '^[[:space:]]*SetEnv[[:space:]]' "$file" | awk '{print $2}' | paste -sd ',' -)"
  ours="$(grep -nE '^# (BEGIN|END) GEST-CONF' "$file" | cut -d: -f1 | paste -sd '-' -)"
  printf '%s' "${passenger:-aucune directive Passenger}"
  if [[ -n "$setenv" ]]; then printf ' ; SetEnv : %s (valeurs masquées)' "$setenv"; fi
  if [[ -n "$ours" ]]; then printf ' ; bloc GEST-CONF lignes %s' "$ours"; fi
}

main() {
  # Aucune commande ne doit lire l'entrée standard (script éventuellement reçu par « bash -s »).
  exec </dev/null

  while (($# > 0)); do
    case "$1" in
      --app-dir) APP_DIR="${2:?--app-dir DIR}"; shift 2 ;;
      --env-file) ENV_FILE="${2:?--env-file FICHIER}"; shift 2 ;;
      --public-dir) PUBLIC_DIR="${2:?--public-dir DIR}"; shift 2 ;;
      --no-network) NETWORK=0; shift ;;
      -h | --help) usage; return 0 ;;
      *) echo "Option inconnue : $1 (voir --help)" >&2; return 2 ;;
    esac
  done
  APP_DIR="${APP_DIR%/}"
  ENV_FILE="${ENV_FILE:-$APP_DIR/.env}"

  trap cleanup EXIT
  trap 'exit 130' INT TERM
  WORK="$(mktemp -d "$HOME/.gestconf-check.XXXXXX" 2>/dev/null || mktemp -d)" || {
    echo "Impossible de créer un dossier temporaire." >&2
    return 2
  }
  write_helpers
  export PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1

  echo "Vérifications o2switch (GEST-CONF, étape L1.0) : lecture seule, aucun secret affiché."
  echo "Application : $APP_DIR ; .env : $ENV_FILE ; racine web : $PUBLIC_DIR"
  echo "Dossier temporaire (supprimé à la fin) : $WORK"

  # --- Système ------------------------------------------------------------------------
  section "Système"
  local os_name
  os_name="$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release 2>/dev/null | tr -d '"')"
  report V00 INFO "Système" "${os_name:-inconnu} ; noyau $(uname -srm) ; hôte $(hostname)"

  local pythons=() python version listing=() best="" best_version="" app_activate app_python=""
  mapfile -t pythons < <(list_pythons)
  for python in "${pythons[@]}"; do
    version="$(python_version "$python")" || continue
    listing+=("$version ($python)")
    case "$version" in
      3.12.*) if [[ "$best_version" != 3.12.* ]]; then best="$python" best_version="$version"; fi ;;
      3.13.*) if [[ -z "$best" ]]; then best="$python" best_version="$version"; fi ;;
    esac
  done
  if [[ -n "$best" ]]; then
    report V01 OK "Python 3.12 ou 3.13 disponible" "$(join_by ' ; ' "${listing[@]}")"
  else
    report V01 ÉCHEC "Python 3.12 ou 3.13 disponible" "$(join_by ' ; ' "${listing[@]}" "aucun 3.12 ni 3.13")"
  fi

  local glibc
  glibc="$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')"
  if [[ -z "$glibc" ]]; then glibc="$(ldd --version 2>/dev/null | sed -n '1s/.* \([0-9][0-9.]*\)$/\1/p')"; fi
  if [[ -z "$glibc" ]]; then
    report V02 ÉCHEC "glibc >= 2.17 (roues manylinux2014)" "version introuvable"
  elif version_ge "$glibc" 2.17; then
    local note="roues manylinux_2_28 non utilisables"
    if version_ge "$glibc" 2.28; then note="roues manylinux_2_28 utilisables"; fi
    report V02 OK "glibc >= 2.17 (roues manylinux2014)" "glibc $glibc ; $note"
  else
    report V02 ÉCHEC "glibc >= 2.17 (roues manylinux2014)" "glibc $glibc"
  fi

  # --- Python : venv jetable et paquets binaires --------------------------------------
  section "Python : venv jetable et paquets binaires"
  app_activate="$(app_venv_activate)"
  if [[ -n "$app_activate" && -x "$(dirname "$app_activate")/python" ]]; then
    app_python="$(dirname "$app_activate")/python"
  fi
  # Même interpréteur que l'application si son venv existe, sinon le meilleur trouvé.
  local base_python="${app_python:-$best}" venv_python=""
  if ((NETWORK == 0)); then
    report V03 INFO "cryptography et fido2 en roues binaires" "non exécuté (--no-network)"
    report V04 INFO "Dépendances verrouillées installables en roues" "non exécuté (--no-network)"
  elif [[ -z "$base_python" ]]; then
    report V03 ÉCHEC "cryptography et fido2 en roues binaires" "aucun Python 3.12/3.13 pour créer le venv"
  elif ! "$base_python" -m venv "$WORK/venv" >"$WORK/venv.log" 2>&1; then
    report V03 ÉCHEC "cryptography et fido2 en roues binaires" \
      "création du venv impossible avec $base_python : $(tail -n 1 "$WORK/venv.log")"
  else
    venv_python="$WORK/venv/bin/python"
    if with_timeout 600 "$venv_python" -m pip install --quiet --no-cache-dir --only-binary=:all: \
      "${CRYPTO_REQUIREMENTS[@]}" >"$WORK/pip-crypto.log" 2>&1; then
      local crypto_info
      if crypto_info="$("$venv_python" - 2>&1 <<'PY'
import importlib.metadata as metadata

from cryptography.fernet import Fernet
from cryptography.hazmat.backends.openssl.backend import backend

import fido2  # noqa: F401

key = Fernet(Fernet.generate_key())
assert key.decrypt(key.encrypt(b"gestconf")) == b"gestconf"
wheel = metadata.distribution("cryptography").read_text("WHEEL") or ""
tags = ",".join(line.split(":", 1)[1].strip() for line in wheel.splitlines() if line.startswith("Tag:"))
print(
    f"cryptography {metadata.version('cryptography')} ({tags}), fido2 {metadata.version('fido2')}, "
    f"{backend.openssl_version_text()}"
)
PY
)"; then
        report V03 OK "cryptography et fido2 en roues binaires (venv jetable, $(python_version "$venv_python"))" \
          "$crypto_info ; chiffrement Fernet testé"
      else
        report V03 ÉCHEC "cryptography et fido2 en roues binaires" "installés mais import impossible : $(tail -n 1 <<<"$crypto_info")"
      fi
    else
      report V03 ÉCHEC "cryptography et fido2 en roues binaires" "$(tail -n 2 "$WORK/pip-crypto.log" | paste -sd ' ' -)"
    fi

    if [[ -f "$APP_DIR/requirements/prod.txt" ]]; then
      # Le pip de deploy.sh est celui du venv de l'application : c'est lui qu'on essaie s'il
      # existe (--dry-run n'installe rien ; pip >= 22.2 requis pour cette option).
      local pip_python="${app_python:-$venv_python}" pip_version
      pip_version="$("$pip_python" -m pip --version 2>/dev/null | awk '{print $2}')"
      if with_timeout 600 "$pip_python" -m pip install --dry-run --quiet --no-cache-dir --require-hashes \
        --only-binary=:all: -r "$APP_DIR/requirements/prod.txt" >"$WORK/pip-prod.log" 2>&1; then
        report V04 OK "Dépendances verrouillées installables en roues (prod.txt, empreintes vérifiées)" \
          "pip ${pip_version:-?} de $pip_python ; pip install --dry-run --require-hashes --only-binary=:all:"
      else
        report V04 ÉCHEC "Dépendances verrouillées installables en roues (prod.txt)" \
          "pip ${pip_version:-?} de $pip_python (--dry-run exige pip >= 22.2) ; $(tail -n 2 "$WORK/pip-prod.log" | paste -sd ' ' -)"
      fi
    else
      report V04 INFO "Dépendances verrouillées installables en roues" \
        "non exécuté : $APP_DIR/requirements/prod.txt absent (application non déployée)"
    fi
  fi

  # --- MariaDB ------------------------------------------------------------------------
  section "MariaDB (identifiants lus dans le .env, jamais affichés)"
  # Préférence : le venv de l'application (PyMySQL installé par deploy.sh depuis prod.txt,
  # empreintes vérifiées) ; sinon un venv dédié ne contenant que PyMySQL, version et
  # empreintes de prod.txt. Jamais le venv de V03.
  local db_python="" db_source=""
  if [[ -n "$app_python" ]] && "$app_python" -c 'import pymysql' >/dev/null 2>&1; then
    db_python="$app_python" db_source="venv de l'application"
  elif ((NETWORK == 1)) && [[ -n "$base_python" ]] && "$base_python" -m venv "$WORK/venv-db" >/dev/null 2>&1; then
    printf '%s\n' "$PYMYSQL_REQUIREMENT" >"$WORK/pymysql-requirements.txt"
    if with_timeout 300 "$WORK/venv-db/bin/python" -m pip install --quiet --no-cache-dir --require-hashes \
      --no-deps --only-binary=:all: -r "$WORK/pymysql-requirements.txt" >"$WORK/pip-pymysql.log" 2>&1; then
      db_python="$WORK/venv-db/bin/python" db_source="venv dédié, PyMySQL de prod.txt (empreintes vérifiées)"
    fi
  fi
  if [[ ! -r "$ENV_FILE" ]]; then
    report V05 ÉCHEC "Connexion à MariaDB" "fichier .env absent ou illisible : $ENV_FILE (deploy/README.md §1)"
  elif [[ -z "$db_python" ]]; then
    report V05 ÉCHEC "Connexion à MariaDB" \
      "PyMySQL indisponible (ni venv de l'application, ni venv dédié : $(tail -n 1 "$WORK/pip-pymysql.log" 2>/dev/null || echo 'réseau désactivé ?'))"
  else
    echo "  (contrôles MariaDB exécutés par $db_python : $db_source)"
    local id status label detail lines=0
    while IFS=$'\t' read -r id status label detail; do
      report "$id" "$status" "$label" "$detail"
      lines=$((lines + 1))
    done < <(with_timeout 180 "$db_python" "$WORK/db_checks.py" "$ENV_FILE" "$EXPECTED_SQL_MODE" \
      "$EXPECTED_COLLATION" 2>"$WORK/db.err")
    if ((lines == 0)); then
      report V05 ÉCHEC "Connexion à MariaDB" "programme de contrôle interrompu sans résultat"
    fi
  fi

  # --- Fichiers et verrous ------------------------------------------------------------
  section "Fichiers et verrous"
  local lock_dir="$WORK" lock_note="dossier temporaire du script ($APP_DIR/tmp absent)"
  if [[ -d "$APP_DIR/tmp" && -w "$APP_DIR/tmp" ]]; then
    lock_dir="$APP_DIR/tmp" lock_note="$APP_DIR/tmp (emplacement des verrous de LockedCommand)"
  fi
  local flock_python="${venv_python:-${best:-$app_python}}" flock_result fs_type
  fs_type="$(filesystem "$lock_dir")"
  if [[ -z "$flock_python" ]]; then
    report V15 ÉCHEC "flock exclusif entre deux processus" "aucun Python pour le test"
  elif LOCK_FILE="$(mktemp "$lock_dir/.gestconf-check-lock.XXXXXX")"; then
    flock_result="$(with_timeout 90 "$flock_python" "$WORK/flock_check.py" "$LOCK_FILE" 2>/dev/null)"
    rm -f -- "$LOCK_FILE"
    LOCK_FILE=""
    if [[ "$flock_result" == "busy acquired" ]]; then
      report V15 OK "flock exclusif entre deux processus" "$lock_note ; système de fichiers $fs_type"
    else
      report V15 ÉCHEC "flock exclusif entre deux processus" \
        "résultat « ${flock_result:-aucun} » (attendu « busy acquired ») ; $lock_note ; $fs_type"
    fi
  else
    report V15 ÉCHEC "flock exclusif entre deux processus" "fichier temporaire impossible dans $lock_dir"
  fi

  local mounts=() target
  for target in /tmp "$HOME" "$APP_DIR"; do
    if [[ -e "$target" ]]; then mounts+=("$target : $(filesystem "$target")"); fi
  done
  report V16 INFO "Systèmes de fichiers (/tmp, \$HOME, application)" "$(join_by ' ; ' "${mounts[@]}")"

  # --- Outils -------------------------------------------------------------------------
  section "Outils"
  if command -v msgfmt >/dev/null; then
    report V17 INFO "gettext (msgfmt)" "présent : $(msgfmt --version 2>/dev/null | sed -n 1p) ; les .mo restent versionnés"
  else
    report V17 INFO "gettext (msgfmt)" "absent ; sans effet : les .mo sont versionnés"
  fi
  local dump
  dump="$(command -v mariadb-dump || command -v mysqldump)"
  if [[ -n "$dump" ]]; then
    report V18 OK "mysqldump / mariadb-dump (sauvegarde de la base)" "$dump : $("$dump" --version 2>/dev/null | sed -n 1p)"
  else
    report V18 ÉCHEC "mysqldump / mariadb-dump (sauvegarde de la base)" "introuvable dans le PATH"
  fi

  # --- Réseau sortant -----------------------------------------------------------------
  section "Accès HTTPS sortant"
  if ((NETWORK == 0)); then
    report V19 INFO "HTTPS sortant vers api.brevo.com" "non exécuté (--no-network)"
    report V20 INFO "HTTPS sortant vers api.mailjet.com" "non exécuté (--no-network)"
    report V21 INFO "HTTPS sortant vers PyPI" "non exécuté (--no-network)"
  elif ! command -v curl >/dev/null; then
    report V19 ÉCHEC "HTTPS sortant (curl)" "curl introuvable"
  else
    https_check V19 "HTTPS sortant vers api.brevo.com (D10)" https://api.brevo.com/v3/account
    https_check V20 "HTTPS sortant vers api.mailjet.com (D10)" https://api.mailjet.com/v3/REST/user
    https_check V21 "HTTPS sortant vers PyPI (pip install du déploiement)" \
      https://pypi.org/simple/pip/ https://files.pythonhosted.org/
  fi

  # --- Application et cPanel ----------------------------------------------------------
  section "Application et cPanel"
  local all_venvs=()
  mapfile -t all_venvs < <(find "$HOME/virtualenv" -maxdepth 5 -type f -path '*/bin/activate' 2>/dev/null | sort)
  local venv_list="aucun"
  if ((${#all_venvs[@]} > 0)); then venv_list="$(join_by ' , ' "${all_venvs[@]}")"; fi
  if [[ -n "$app_activate" ]]; then
    report V22 OK "Venv cPanel de l'application (DEPLOY_VENV_ACTIVATE, cron)" \
      "$app_activate (Python $(python_version "$app_python") ; $("$app_python" -m pip --version 2>/dev/null | awk '{print "pip " $2}'))"
  else
    report V22 ÉCHEC "Venv cPanel de l'application (DEPLOY_VENV_ACTIVATE, cron)" \
      "aucun sous $HOME/virtualenv/${APP_DIR#"$HOME"/}/ ; venvs trouvés : $venv_list"
  fi

  if [[ -f "$ENV_FILE" ]]; then
    local mode env_real public_real problems=()
    mode="$(stat -c '%a' "$ENV_FILE")"
    env_real="$(readlink -f -- "$ENV_FILE")"
    public_real="$(readlink -f -- "$PUBLIC_DIR")"
    if (((8#$mode & 8#077) != 0)); then problems+=("droits $mode : chmod 600 $ENV_FILE"); fi
    if [[ -n "$public_real" && "$env_real" == "$public_real"/* ]]; then problems+=("DANS la racine web"); fi
    if ((${#problems[@]} == 0)); then
      report V23 OK "Fichier .env : droits 600, hors racine web" "droits $mode"
    else
      report V23 ÉCHEC "Fichier .env : droits 600, hors racine web" "$(join_by ' ; ' "${problems[@]}")"
    fi
  else
    report V23 ÉCHEC "Fichier .env : droits 600, hors racine web" "absent : $ENV_FILE"
  fi

  local htaccess found_passenger=0
  for htaccess in "$PUBLIC_DIR/.htaccess" "$PUBLIC_DIR/api/.htaccess"; do
    [[ -f "$htaccess" ]] || continue
    if grep -qE '^[[:space:]]*Passenger[A-Za-z]+' "$htaccess"; then found_passenger=1; fi
    report V24 INFO "Directives de $htaccess" "$(htaccess_summary "$htaccess")"
  done
  if ((found_passenger)); then
    report V24 OK "Bloc Passenger trouvé (emplacement ci-dessus, à reporter dans la fiche)"
  else
    report V24 ÉCHEC "Bloc Passenger introuvable" \
      "ni $PUBLIC_DIR/.htaccess ni $PUBLIC_DIR/api/.htaccess (application créée dans cPanel ?)"
  fi

  if [[ -n "$app_python" && -f "$APP_DIR/manage.py" && -r "$ENV_FILE" ]]; then
    local check_output check_rc check_summary
    # GESTCONF_ENV_FILE : le même .env que les contrôles MariaDB (option --env-file).
    check_output="$(cd "$APP_DIR" && DJANGO_SETTINGS_MODULE=config.settings.prod GESTCONF_ENV_FILE="$ENV_FILE" \
      with_timeout 120 "$app_python" manage.py check --database default --tag database 2>&1)"
    check_rc=$?
    # Filtre : seuls les codes de contrôle et le bilan sont affichés.
    check_summary="$(grep -Eo 'mysql\.[EW][0-9]+|System check identified (no|[0-9]+) issues?' <<<"$check_output" \
      | sort -u | paste -sd '|' - | sed 's/|/ ; /g')"
    if ((check_rc == 0)) && ! grep -q 'mysql\.W002' <<<"$check_output"; then
      report V25 OK "check --database default (mysql.W002 absent)" "${check_summary:-sans message}"
    elif ((check_rc == 0)); then
      report V25 ÉCHEC "check --database default (mysql.W002 absent)" \
        "mysql.W002 : mode strict absent (code déployé antérieur à L1.1 ?) ; $check_summary"
    else
      report V25 ÉCHEC "check --database default" \
        "code $check_rc ; sortie masquée, relancer à la main dans le venv : python manage.py check --database default --tag database"
    fi
  else
    report V25 INFO "check --database default" "non exécuté : application non déployée (manage.py, venv ou .env absent)"
  fi

  # --- Ressources ---------------------------------------------------------------------
  section "Ressources du compte"
  local processes passenger_count
  processes="$(ps -u "$(id -u)" -o args= 2>/dev/null)"
  passenger_count="$(grep -cE '[Pp]assenger|wsgi-loader' <<<"$processes")"
  report V26 INFO "Processus et limites du compte" \
    "processus Passenger visibles : $passenger_count (selon le trafic récent) ; CPU : $(nproc 2>/dev/null || echo '?') ; ulimit -u $(ulimit -u) ; ulimit -v $(ulimit -v) ; limites CloudLinux : voir cPanel"

  # --- Récapitulatif ------------------------------------------------------------------
  printf '\n%s\n' "========================================================================"
  echo "Récapitulatif à reporter dans docs/L1-verifications-o2switch.md (colonne « Obtenu »)"
  echo "Relevé du $(date -u '+%Y-%m-%d %H:%M UTC') sur $(hostname)"
  echo "========================================================================"
  printf '%s\n' "${SUMMARY[@]}" | sort -s -k1,1
  echo "Bilan : $COUNT_OK OK, $COUNT_FAIL ÉCHEC, $COUNT_INFO INFO."
  ((COUNT_FAIL == 0))
}

main "$@"; exit $?
