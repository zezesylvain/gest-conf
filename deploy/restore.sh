#!/usr/bin/env bash
# Restauration d'une sauvegarde (plan L9, S3 ; étude §11.6, test de restauration documenté).
#
# Usage : deploy/restore.sh <gestconf-<date>.sql.gz> [<instantané de fichiers>]
#
# À lancer avec un environnement qui désigne une base NEUVE et des dossiers VIDES :
#   - DATABASE_URL : base vide (restore_db refuse une base qui contient des tables) ;
#   - GESTCONF_FILES_DIR (et GESTCONF_PRIVATE_FILES_DIR s'il est séparé) : dossiers vides ;
#   - le manifeste gestconf-<date>.json à côté du dump (empreinte vérifiée).
# Sur l'hébergement : le venv de l'application est chargé (fichier VENV_ACTIVATE) et la
# configuration de production lue ; sur le poste de l'opérateur : venv backend/.venv et
# configuration de développement, sauf DJANGO_SETTINGS_MODULE déjà défini.
#
# Étapes : restore_db (dump, fichiers, comparaison au manifeste, tables du cache, migrations
# en attente signalées), puis check_integrity. Durée affichée : à comparer à l'objectif de
# rétablissement (4 heures, étude §11.6).
set -euo pipefail

dump="${1:?Usage : $0 <dump.sql.gz> [<instantané de fichiers>]}"
files="${2:-}"
dump="$(cd "$(dirname "$dump")" && pwd)/$(basename "$dump")"
if [[ -n "$files" ]]; then
  files="$(cd "$files" && pwd)"
fi

root="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -f "$root/manage.py" ]]; then
  # Dossier de l'application sur l'hébergement (deploy/ livré par deploy.sh).
  app="$root"
  # shellcheck disable=SC1090
  source "$(<"$app/VENV_ACTIVATE")"
  export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"
else
  # Dépôt sur le poste de l'opérateur.
  app="$root/backend"
  # shellcheck disable=SC1091
  source "$app/.venv/bin/activate"
fi
cd "$app"

started="$(date +%s)"
arguments=("$dump")
if [[ -n "$files" ]]; then
  arguments+=(--files-from "$files")
fi
python manage.py restore_db "${arguments[@]}"
# check_integrity rend 0 même avec des anomalies (il alerte les opérateurs) : la restauration
# échoue ici si une ligne en compte au moins une (constat du runbook, L9.7). Sauf les
# contrôles de l'environnement : juste après une restauration, la sauvegarde est forcément
# « absente ou en retard » (son battement n'est pas dans le dump) et le disque est celui du
# poste où l'on restaure.
integrity_log="$(mktemp)"
trap 'rm -f "$integrity_log"' EXIT
python manage.py check_integrity | tee "$integrity_log"
elapsed=$(($(date +%s) - started))
printf '\nRestauration terminée en %d min %02d s (objectif : moins de 4 h).\n' \
  $((elapsed / 60)) $((elapsed % 60))
if grep -E -- '-> [1-9][0-9]* anomalie' "$integrity_log" |
  grep -Evq 'core\.(backup_age|disk_space) '; then
  printf "Anomalies d'intégrité après restauration : voir les lignes ci-dessus.\n" >&2
  exit 1
fi
