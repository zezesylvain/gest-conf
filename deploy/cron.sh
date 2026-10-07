#!/usr/bin/env bash
# Point d'entrée unique des tâches cron de GEST-CONF (plan L1 §8.4 ; deploy/README.md §5).
#
# Usage (lignes de cron cPanel) :
#   */5 * * * *  /home/compte/gestconf-app/deploy/cron.sh run_jobs --max-seconds 240
#   17 3 * * *   /home/compte/gestconf-app/deploy/cron.sh cleanup
#
# Le script ne fait qu'une chose : lancer « manage.py <commande> [options] » dans les mêmes
# conditions que Passenger.
# - Même code : le dossier de l'application est le parent du dossier de ce script
#   (<application>/deploy/cron.sh, copié là par deploy.sh).
# - Même venv : script « activate » du venv cPanel, GESTCONF_VENV_ACTIVATE, que deploy.sh écrit
#   dans <application>/cron.conf à chaque déploiement (le venv où pip vient d'installer les
#   dépendances, celui de DEPLOY_VENV_ACTIVATE). À défaut, le seul venv trouvé sous
#   ~/virtualenv/<application>/<version>/bin/activate (convention de « Setup Python App ») ;
#   s'il y en a plusieurs, le script refuse de choisir.
# - Même .env : celui que lisent les réglages Django eux-mêmes (<application>/.env, ou
#   GESTCONF_ENV_FILE). Le script vérifie qu'il est lisible, mais ne le lit pas : il n'est
#   jamais interprété par le shell.
# - Mêmes réglages : DJANGO_SETTINGS_MODULE=config.settings.prod, imposé (manage.py prendrait
#   sinon config.settings.dev) ; les options --settings et --pythonpath sont refusées.
#
# Commandes autorisées : liste blanche ALLOWED_COMMANDS. Ce sont toutes des LockedCommand
# (verrou exclusif, battement de cœur), ce que vérifie backend/tests/test_cron_script.py.
#
# Configuration facultative, <application>/cron.conf (hors dépôt, exclu du rsync, droits 600) :
# lignes « CLÉ=valeur » sans guillemets ni développement, commentaires « # », chemins absolus.
# Clés reconnues :
#   GESTCONF_VENV_ACTIVATE        script activate du venv (écrit par deploy.sh)
#   GESTCONF_ENV_FILE             .env à faire lire par Django (défaut : <application>/.env)
#   GESTCONF_CRON_LOG             journal (défaut : <application>/logs/cron.log)
#   GESTCONF_CRON_LOG_MAX_BYTES   taille déclenchant la rotation (défaut : 1048576)
# Une variable du même nom dans l'environnement (ligne de cron) l'emporte sur cron.conf.
#
# Journal : chaque ligne est préfixée par l'heure UTC, la commande et le PID. Rotation simple :
# au-delà de la taille maximale, cron.log devient cron.log.1 (une seule archive). Deux tâches
# qui tournent en même temps écrivent dans le même journal ; leurs lignes restent distinctes
# grâce au préfixe.
#
# Sorties : rien sur la sortie standard. En cas d'échec, une seule ligne sur la sortie d'erreur,
# sans détail (le détail est dans le journal) : cPanel l'envoie à l'adresse « E-mail du cron ».
# Code de sortie : celui de manage.py ; 64 si l'appel est invalide (commande hors liste, option
# interdite) ; 78 si la configuration est incomplète (venv, .env, cron.conf).

set -euo pipefail
umask 077
export TZ=UTC

readonly ALLOWED_COMMANDS=(run_jobs cleanup)
readonly CONF_KEYS=(GESTCONF_VENV_ACTIVATE GESTCONF_ENV_FILE GESTCONF_CRON_LOG GESTCONF_CRON_LOG_MAX_BYTES)
readonly EX_USAGE=64 EX_CONFIG=78

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname -- "$SCRIPT_DIR")"
CONF_FILE="$APP_DIR/cron.conf"
# Journal par défaut, tant que la configuration n'est pas validée.
LOG_FILE="$APP_DIR/logs/cron.log"
COMMAND="cron.sh"

usage() {
  printf 'Usage : %s <commande> [options de la commande]\nCommandes autorisées : %s\n' \
    "$0" "${ALLOWED_COMMANDS[*]}"
}

# log <message> : une ligne horodatée dans le journal (si son dossier est accessible).
log() {
  { printf '%(%Y-%m-%dT%H:%M:%SZ)T %s[%d] %s\n' -1 "$COMMAND" "$$" "$1" >>"$LOG_FILE"; } 2>/dev/null || true
}

# log_lines : préfixe chaque ligne lue sur l'entrée standard et l'ajoute au journal.
log_lines() {
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%(%Y-%m-%dT%H:%M:%SZ)T %s[%d] %s\n' -1 "$COMMAND" "$$" "$line"
  done >>"$LOG_FILE"
}

# fail <code> <message> : sortie d'erreur (e-mail du cron) et journal.
fail() {
  printf 'cron.sh : %s\n' "$2" >&2
  log "ERREUR : $2"
  exit "$1"
}

# --- 1. Appel : commande en liste blanche, réglages non surchargeables ----------------------
if (($# == 0)); then
  usage >&2
  exit "$EX_USAGE"
fi
case "$1" in
  -h | --help)
    usage
    exit 0
    ;;
esac
allowed=0
for candidate in "${ALLOWED_COMMANDS[@]}"; do
  if [[ "$1" == "$candidate" ]]; then allowed=1; fi
done
if ((allowed == 0)); then
  # Rien n'est écrit dans le journal avec une commande inconnue : son nom n'est pas fiable.
  printf 'cron.sh : commande non autorisée « %s » (autorisées : %s)\n' "$1" "${ALLOWED_COMMANDS[*]}" >&2
  exit "$EX_USAGE"
fi
COMMAND="$1"
shift
for arg in "$@"; do
  # Toute abréviation de --settings ou --pythonpath est refusée : les réglages de production
  # (et le code chargé) ne se choisissent pas sur la ligne de cron.
  option="${arg%%=*}"
  if [[ ${#option} -ge 3 && ("--settings" == "$option"* || "--pythonpath" == "$option"*) ]]; then
    printf 'cron.sh : option interdite « %s » (réglages imposés : config.settings.prod)\n' "$option" >&2
    exit "$EX_USAGE"
  fi
done

# --- 2. Configuration : cron.conf (lu, jamais exécuté), puis détection -----------------------
declare -A conf=()
if [[ -e "$CONF_FILE" ]]; then
  # cron.conf désigne un script qui sera exécuté (activate) : il doit appartenir au compte et
  # n'être modifiable par personne d'autre.
  owner="$(stat -L -c '%u' -- "$CONF_FILE")"
  mode="$(stat -L -c '%a' -- "$CONF_FILE")"
  if [[ "$owner" != "$(id -u)" ]] || (((8#$mode & 8#022) != 0)); then
    fail "$EX_CONFIG" "$CONF_FILE doit appartenir au compte et n'être modifiable que par lui (chmod 600)"
  fi
  line_number=0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line_number=$((line_number + 1))
    line="${line%$'\r'}"
    if [[ "$line" =~ ^[[:space:]]*(#.*)?$ ]]; then continue; fi
    if [[ ! "$line" =~ ^([A-Z_]+)=(.*)$ ]]; then
      fail "$EX_CONFIG" "$CONF_FILE, ligne $line_number : « CLÉ=valeur » attendu"
    fi
    key="${BASH_REMATCH[1]}"
    if [[ " ${CONF_KEYS[*]} " != *" $key "* ]]; then
      fail "$EX_CONFIG" "$CONF_FILE, ligne $line_number : clé inconnue $key (reconnues : ${CONF_KEYS[*]})"
    fi
    conf[$key]="${BASH_REMATCH[2]}"
  done <"$CONF_FILE"
fi
: "${GESTCONF_VENV_ACTIVATE:=${conf[GESTCONF_VENV_ACTIVATE]:-}}"
: "${GESTCONF_ENV_FILE:=${conf[GESTCONF_ENV_FILE]:-}}"
: "${GESTCONF_CRON_LOG:=${conf[GESTCONF_CRON_LOG]:-$APP_DIR/logs/cron.log}}"
: "${GESTCONF_CRON_LOG_MAX_BYTES:=${conf[GESTCONF_CRON_LOG_MAX_BYTES]:-1048576}}"

for key in GESTCONF_VENV_ACTIVATE GESTCONF_ENV_FILE GESTCONF_CRON_LOG; do
  if [[ -n "${!key}" && "${!key}" != /* ]]; then
    fail "$EX_CONFIG" "$key doit être un chemin absolu : ${!key}"
  fi
done
# Vérifié avant tout usage arithmétique : bash évaluerait le contenu de la variable.
if [[ ! "$GESTCONF_CRON_LOG_MAX_BYTES" =~ ^[0-9]+$ ]]; then
  fail "$EX_CONFIG" "GESTCONF_CRON_LOG_MAX_BYTES doit être un nombre d'octets"
fi

LOG_FILE="$GESTCONF_CRON_LOG"
if ! mkdir -p -- "$(dirname -- "$LOG_FILE")"; then
  fail "$EX_CONFIG" "dossier du journal impossible à créer : $(dirname -- "$LOG_FILE")"
fi
# Rotation simple. Deux tâches simultanées peuvent tourner ensemble : au pire, une archive
# est remplacée par un journal presque vide (perte bornée à une archive, assumée).
if [[ -f "$LOG_FILE" ]] && (($(wc -c <"$LOG_FILE") >= 10#$GESTCONF_CRON_LOG_MAX_BYTES)); then
  mv -f -- "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
fi

if [[ ! -f "$APP_DIR/manage.py" ]]; then
  fail "$EX_CONFIG" "manage.py absent de $APP_DIR : cron.sh doit être lancé depuis <application>/deploy/"
fi

if [[ -z "$GESTCONF_VENV_ACTIVATE" ]]; then
  relative="${APP_DIR#"${HOME:-}"/}"
  shopt -s nullglob
  candidates=("${HOME:-}/virtualenv/$relative"/*/bin/activate)
  shopt -u nullglob
  if ((${#candidates[@]} == 1)); then
    GESTCONF_VENV_ACTIVATE="${candidates[0]}"
  elif ((${#candidates[@]} == 0)); then
    fail "$EX_CONFIG" "aucun venv sous ~/virtualenv/$relative/ : renseigner GESTCONF_VENV_ACTIVATE dans $CONF_FILE (ou relancer deploy.sh)"
  else
    fail "$EX_CONFIG" "plusieurs venvs (${candidates[*]}) : renseigner dans $CONF_FILE celui de « Setup Python App » (GESTCONF_VENV_ACTIVATE)"
  fi
fi
PYTHON="$(dirname -- "$GESTCONF_VENV_ACTIVATE")/python"
if [[ ! -f "$GESTCONF_VENV_ACTIVATE" || ! -x "$PYTHON" ]]; then
  fail "$EX_CONFIG" "venv invalide : $GESTCONF_VENV_ACTIVATE (script activate et python exécutable attendus)"
fi

env_file="${GESTCONF_ENV_FILE:-$APP_DIR/.env}"
if [[ ! -r "$env_file" ]]; then
  fail "$EX_CONFIG" "fichier .env introuvable ou illisible : $env_file (deploy/README.md §1)"
fi
if [[ -n "$GESTCONF_ENV_FILE" ]]; then
  export GESTCONF_ENV_FILE
fi

# --- 3. Exécution ----------------------------------------------------------------------------
export DJANGO_SETTINGS_MODULE=config.settings.prod
# Sortie en UTF-8 (messages en français) quelle que soit la locale du cron, et sans tampon :
# les lignes de la sortie standard et de la sortie d'erreur restent dans l'ordre du journal.
export PYTHONIOENCODING=utf-8 PYTHONUNBUFFERED=1

release="$(cat -- "$APP_DIR/RELEASE" 2>/dev/null || echo inconnue)"
log "début : manage.py $COMMAND $* (version $release ; venv $GESTCONF_VENV_ACTIVATE)"
started=$SECONDS
set +e
(
  # Même venv que deploy.sh et que les consignes de cPanel : activate, puis son python.
  set +eu
  # shellcheck disable=SC1090  # chemin connu à l'exécution seulement
  source "$GESTCONF_VENV_ACTIVATE"
  set -eu
  cd -- "$APP_DIR"
  exec "$PYTHON" manage.py "$COMMAND" "$@"
) </dev/null 2>&1 | log_lines
status=${PIPESTATUS[0]}
set -e
log "fin : code $status en $((SECONDS - started)) s"
if ((status != 0)); then
  printf 'cron.sh : « %s » a échoué (code %d) ; détail dans %s\n' "$COMMAND" "$status" "$LOG_FILE" >&2
fi
exit "$status"
