#!/usr/bin/env bash
# Commandes planifiées de GEST-CONF (règle n° 9 de CLAUDE.md, plan L1 §8.4).
#
# Déployé par deploy.sh dans ~/<application>/deploy/cron.sh. Crontab cPanel (minutes
# décalées pour éviter les heures pleines ; intervalle de run_jobs selon H-6/M01) :
#   */5 * * * *  $HOME/gestconf-app/deploy/cron.sh run_jobs --max-seconds 240
#   11 * * * *   $HOME/gestconf-app/deploy/cron.sh close_call
#   13 * * * *   $HOME/gestconf-app/deploy/cron.sh remind_drafts
#   17 3 * * *   $HOME/gestconf-app/deploy/cron.sh cleanup
#   47 3 * * *   $HOME/gestconf-app/deploy/cron.sh check_integrity
#
# Charge le MÊME venv que Passenger (chemin écrit par deploy.sh dans VENV_ACTIVATE) et le
# même .env (lu par config.settings.prod). Toute la sortie va dans logs/cron-<commande>.log :
# rien n'est écrit sur la sortie standard, pour que cron n'envoie pas d'e-mail à chaque passage.
# Les commandes sont verrouillées et idempotentes (LockedCommand) : un chevauchement sort
# proprement, sans rien faire.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
command="${1:?Usage : $0 <commande> [options]}"

# Liste fermée : ce script n'est pas un accès générique à manage.py.
case "$command" in
  run_jobs | close_call | remind_drafts | cleanup | check_integrity) ;;
  *)
    echo "Commande non planifiable : $command" >&2
    exit 2
    ;;
esac

venv_file="$APP_DIR/VENV_ACTIVATE"
if [[ ! -f "$venv_file" ]]; then
  echo "$venv_file absent : relancer deploy/deploy.sh (DEPLOY_VENV_ACTIVATE)." >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$(<"$venv_file")"
cd "$APP_DIR"
export DJANGO_SETTINGS_MODULE=config.settings.prod

mkdir -p logs
log="logs/cron-$command.log"
# Rotation minimale : au-delà de 5 Mio, le journal courant devient .1 (l'ancien .1 est perdu).
if [[ -f "$log" ]] && (($(stat -c %s "$log") > 5242880)); then
  mv -f "$log" "$log.1"
fi

started="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
if python manage.py "$@" --verbosity 1 >>"$log" 2>&1; then
  status=0
else
  status=$?
fi
printf '%s %s : code de sortie %s\n' "$started" "$command" "$status" >>"$log"
exit "$status"
