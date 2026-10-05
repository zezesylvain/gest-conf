#!/usr/bin/env bash
# Déploiement de GEST-CONF sur o2switch (rsync + SSH), étude §11.4.
#
# Prérequis côté serveur (une seule fois, voir deploy/README.md) :
#   - application Python créée dans cPanel (« Setup Python App », URL /api) ;
#   - fichier .env de production déposé dans le dossier de l'application ;
#   - base MariaDB créée (utf8mb4).
#
# Variables :
#   DEPLOY_SSH            compte@serveur (obligatoire)
#   DEPLOY_VENV_ACTIVATE  script « activate » du virtualenv créé par cPanel (obligatoire),
#                         ex. /home/compte/virtualenv/gestconf-app/3.12/bin/activate
#   DEPLOY_APP_DIR        dossier de l'application Django (défaut : gestconf-app)
#   DEPLOY_PUBLIC_DIR     racine web (défaut : public_html)
#   DEPLOY_BASE_URL       URL publique pour les tests de fumée, ex. https://conference.exemple.org
#   SKIP_BUILD=1          réutiliser les builds Angular existants (web/dist)

set -euo pipefail

: "${DEPLOY_SSH:?Définir DEPLOY_SSH (compte@serveur)}"
: "${DEPLOY_VENV_ACTIVATE:?Définir DEPLOY_VENV_ACTIVATE (script activate du venv cPanel)}"
DEPLOY_APP_DIR="${DEPLOY_APP_DIR:-gestconf-app}"
DEPLOY_PUBLIC_DIR="${DEPLOY_PUBLIC_DIR:-public_html}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE="$(git -C "$ROOT" rev-parse --short HEAD)"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

step() { printf '\n==> %s\n' "$*"; }

if [[ -n "$(git -C "$ROOT" status --porcelain)" ]]; then
  echo "Arbre de travail modifié : committer avant de déployer (version tracée = commit)." >&2
  exit 1
fi

# --- 1. Build des applications Angular ------------------------------------------------
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  step "Build Angular (portail pré-rendu + gestion)"
  (cd "$ROOT/web" && npm ci && npx ng build portail && npx ng build gestion)
fi

step "Préparation des fichiers statiques"
mkdir -p "$STAGING/public/gestion"
cp -a "$ROOT/web/dist/portail/browser/." "$STAGING/public/"
cp -a "$ROOT/web/dist/gestion/browser/." "$STAGING/public/gestion/"
cp "$ROOT/deploy/apache/gestion.htaccess" "$STAGING/public/gestion/.htaccess"

# --- 2. Backend Django ---------------------------------------------------------------
step "Envoi du code Django vers ~/$DEPLOY_APP_DIR (version $RELEASE)"
# --delete évite qu'une migration supprimée du dépôt reste sur le serveur ; les
# exclusions protègent ce qui n'appartient qu'au serveur (.env, journaux, fichiers cPanel).
rsync -az --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.ruff_cache/' \
  --exclude '/.env' --exclude '/db.sqlite3' --exclude '/tmp/' --exclude '/RELEASE' \
  --exclude '/public/' --exclude '*.log' \
  "$ROOT/backend/" "$DEPLOY_SSH:$DEPLOY_APP_DIR/"

step "Dépendances, migrations, contrôles, redémarrage de Passenger"
# Le .env de production (hors dépôt) est lu par config.settings.prod.
# Les valeurs locales sont passées en arguments échappés (printf %q) au script distant.
# shellcheck disable=SC2029  # développement côté client voulu
ssh "$DEPLOY_SSH" "bash -s -- $(printf '%q ' "$DEPLOY_VENV_ACTIVATE" "$DEPLOY_APP_DIR" "$RELEASE")" <<'REMOTE'
set -euo pipefail
venv_activate="$1" app_dir="$2" release="$3"
# shellcheck disable=SC1090
source "$venv_activate"
cd "$app_dir"
export DJANGO_SETTINGS_MODULE=config.settings.prod
pip install --quiet -r requirements/prod.txt
python manage.py migrate --noinput
python manage.py check --deploy --fail-level WARNING
echo "$release" > RELEASE
mkdir -p tmp && touch tmp/restart.txt
REMOTE

# --- 3. Fichiers statiques -----------------------------------------------------------
step "Envoi des fichiers statiques vers ~/$DEPLOY_PUBLIC_DIR"
# Exclusions : le .htaccess racine est fusionné à part (bloc Passenger de cPanel),
# api/ peut contenir la configuration Passenger, .well-known/ sert au certificat AutoSSL.
rsync -az --delete \
  --exclude '/.htaccess' --exclude '/api/' --exclude '/.well-known/' --exclude '/cgi-bin/' \
  "$STAGING/public/" "$DEPLOY_SSH:$DEPLOY_PUBLIC_DIR/"

step "Fusion du bloc GEST-CONF dans $DEPLOY_PUBLIC_DIR/.htaccess"
# shellcheck disable=SC2029  # chemin volontairement développé côté client, puis échappé
ssh "$DEPLOY_SSH" "cat $(printf '%q' "$DEPLOY_PUBLIC_DIR/.htaccess") 2>/dev/null || true" \
  > "$STAGING/htaccess.current"
mkdir -p "$ROOT/deploy/backups"
cp "$STAGING/htaccess.current" "$ROOT/deploy/backups/htaccess-$(date +%Y%m%d-%H%M%S)"
python3 "$ROOT/deploy/htaccess_merge.py" "$STAGING/htaccess.current" \
  "$ROOT/deploy/apache/public_html.htaccess" > "$STAGING/htaccess.new"
rsync -az "$STAGING/htaccess.new" "$DEPLOY_SSH:$DEPLOY_PUBLIC_DIR/.htaccess"

# --- 4. Tests de fumée ---------------------------------------------------------------
if [[ -n "${DEPLOY_BASE_URL:-}" ]]; then
  step "Tests de fumée sur $DEPLOY_BASE_URL"
  "$ROOT/deploy/smoke-test.sh" "$DEPLOY_BASE_URL" "$RELEASE"
fi

step "Déploiement $RELEASE terminé"
