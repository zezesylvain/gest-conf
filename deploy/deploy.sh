#!/usr/bin/env bash
# Déploiement de GEST-CONF sur o2switch (rsync + SSH), étude §11.4.
#
# Usage : deploy/deploy.sh                 déploiement complet, puis publication du portail
#         deploy/deploy.sh --portal-only   republication du portail seul (E9, plan L2)
#
# Publication du portail : le portail est pré-rendu à partir de l'API publique de
# production (GESTCONF_PRERENDER_API_ORIGIN, défaut DEPLOY_BASE_URL), contrôlé (toutes les
# routes annoncées, marqueur de rendu, CSP), synchronisé sans toucher à /gestion/ ni à
# /api/, puis la mise en ligne est enregistrée (manage.py mark_portal_published, datée du
# début du build) : le bandeau « modifications non publiées » de la gestion repart de zéro.
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
#   SKIP_BUILD=1          réutiliser les builds Angular existants (web/dist) ; sans effet
#                         sur la publication du portail, toujours reconstruit
#   GESTCONF_PRERENDER_API_ORIGIN  origine de l'API lue au pré-rendu (défaut : DEPLOY_BASE_URL)
#   SKIP_PORTAL=1         déploiement complet sans publication du portail (portail rendu
#                         dans le navigateur jusqu'au prochain --portal-only)

set -euo pipefail

PORTAL_ONLY=0
case "${1:-}" in
  "") ;;
  --portal-only) PORTAL_ONLY=1 ;;
  *)
    echo "Option inconnue : $1 (seule --portal-only est reconnue)." >&2
    exit 2
    ;;
esac

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

# Publication du portail pré-rendu (E9). Lit l'API publique de production : à lancer une
# fois le backend de cette version en ligne.
publish_portal() {
  local origin="${GESTCONF_PRERENDER_API_ORIGIN:-${DEPLOY_BASE_URL:-}}"
  if [[ -z "$origin" ]]; then
    echo "Publication du portail : définir DEPLOY_BASE_URL (ou GESTCONF_PRERENDER_API_ORIGIN)." >&2
    exit 1
  fi
  origin="${origin%/}"
  step "Pré-rendu du portail à partir de $origin"
  local edition_code built_at
  # Édition courante lue AVANT le build : la mise en ligne est enregistrée pour elle.
  edition_code="$(curl -fsS "$origin/api/v1/public/portal/site" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["edition"]["code"])')"
  built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  # build:portail = pré-rendu, contrôle de complétude (refus de livrer un portail
  # incomplet), plan du site, CSP à empreintes.
  (cd "$ROOT/web" && { [[ -d node_modules ]] || npm ci; } \
    && GESTCONF_PRERENDER_API_ORIGIN="$origin" npm run build:portail)
  local pages_without_csp
  pages_without_csp="$(find "$ROOT/web/dist/portail" -name '*.html' -type f \
    -exec grep -L 'http-equiv="Content-Security-Policy"' {} + || true)"
  if [[ -n "$pages_without_csp" ]]; then
    printf 'CSP absente de : %s\n' "$pages_without_csp" >&2
    exit 1
  fi
  [[ -f "$ROOT/web/dist/portail/browser/sitemap.xml" ]] || {
    echo "Plan du site absent : pré-rendu non effectué." >&2
    exit 1
  }

  step "Envoi du portail vers ~/$DEPLOY_PUBLIC_DIR (gestion/ et api/ intacts)"
  rsync -az --delete \
    --exclude '/.htaccess' --exclude '/api/' --exclude '/gestion/' --exclude '/.well-known/' \
    --exclude '/cgi-bin/' \
    "$ROOT/web/dist/portail/browser/" "$DEPLOY_SSH:$DEPLOY_PUBLIC_DIR/"

  step "Mise en ligne enregistrée ($edition_code, données du $built_at)"
  # shellcheck disable=SC2029  # développement côté client voulu
  ssh "$DEPLOY_SSH" "bash -s -- $(printf '%q ' "$DEPLOY_VENV_ACTIVATE" "$DEPLOY_APP_DIR" \
    "$edition_code" "$RELEASE" "$built_at")" <<'REMOTE'
set -euo pipefail
venv_activate="$1" app_dir="$2" code="$3" release="$4" built_at="$5"
# shellcheck disable=SC1090
source "$venv_activate"
cd "$app_dir"
export DJANGO_SETTINGS_MODULE=config.settings.prod
python manage.py mark_portal_published "$code" --release "$release" --built-at "$built_at"
REMOTE
}

if [[ "$PORTAL_ONLY" == "1" ]]; then
  publish_portal
  if [[ -n "${DEPLOY_BASE_URL:-}" ]]; then
    step "Tests de fumée sur $DEPLOY_BASE_URL"
    # Sans version attendue : le backend en ligne peut être d'une version antérieure.
    "$ROOT/deploy/smoke-test.sh" "$DEPLOY_BASE_URL"
  fi
  step "Portail publié ($RELEASE)"
  exit 0
fi

# --- 1. Build des applications Angular ------------------------------------------------
if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  step "Build Angular (portail pré-rendu + gestion + CSP à empreintes)"
  # « npm run build » et non « ng build » : le script npm ajoute ensuite la CSP à
  # empreintes en <meta> dans chaque page HTML (web/scripts/inject-csp.mjs). Sans
  # elle, aucune restriction des scripts n'est appliquée en production (bug L0).
  (cd "$ROOT/web" && npm ci && npm run build)
fi

# Garde-fou, y compris avec SKIP_BUILD=1 : ne jamais publier une page sans sa CSP. Toutes
# les pages HTML du build sont contrôlées (inject-csp.mjs les traite toutes), y compris les
# pages pré-rendues à venir du portail (dist/portail/browser/<route>/index.html).
for page in "$ROOT/web/dist/portail/browser/index.html" "$ROOT/web/dist/portail/browser/index.csr.html" \
  "$ROOT/web/dist/gestion/browser/index.html"; do
  if [[ ! -f "$page" ]]; then
    echo "Page attendue absente : $page (relancer « npm run build » dans web/)." >&2
    exit 1
  fi
done
# « || true » : grep -L sort en code 1 quand il ne liste aucun fichier (cas normal), ce qui
# arrêterait le script (set -e) ; seule la liste produite compte.
pages_without_csp="$(find "$ROOT/web/dist" -name '*.html' -type f \
  -exec grep -L 'http-equiv="Content-Security-Policy"' {} + || true)"
if [[ -n "$pages_without_csp" ]]; then
  printf 'CSP absente de : %s\nRelancer « npm run build » dans web/.\n' "$pages_without_csp" >&2
  exit 1
fi

step "Préparation des fichiers statiques"
mkdir -p "$STAGING/public/gestion"
cp -a "$ROOT/web/dist/portail/browser/." "$STAGING/public/"
cp -a "$ROOT/web/dist/gestion/browser/." "$STAGING/public/gestion/"
cp "$ROOT/deploy/apache/gestion.htaccess" "$STAGING/public/gestion/.htaccess"

# --- 2. Backend Django ---------------------------------------------------------------
step "Envoi du code Django vers ~/$DEPLOY_APP_DIR (version $RELEASE)"
# Seul le contenu versionné du commit déployé est envoyé (git archive) : aucun fichier
# ignoré par git présent sur le poste (.coverage, htmlcov/, .env.local, db.sqlite3...)
# ne peut partir sur le serveur.
git -C "$ROOT" archive --format=tar "$RELEASE" backend | tar -x -C "$STAGING"
# Script des commandes planifiées (crontab cPanel), versionné lui aussi : extrait du commit.
mkdir -p "$STAGING/backend/deploy"
git -C "$ROOT" show "$RELEASE:deploy/cron.sh" >"$STAGING/backend/deploy/cron.sh"
chmod 755 "$STAGING/backend/deploy/cron.sh"
# --delete évite qu'une migration supprimée du dépôt reste sur le serveur ; les
# exclusions protègent ce qui n'appartient qu'au serveur (.env, journaux, fichiers cPanel).
rsync -az --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '.pytest_cache/' --exclude '.ruff_cache/' \
  --exclude '/.env' --exclude '/db.sqlite3' --exclude '/tmp/' --exclude '/RELEASE' \
  --exclude '/VENV_ACTIVATE' --exclude '/logs/' --exclude '/public/' --exclude '*.log' \
  "$STAGING/backend/" "$DEPLOY_SSH:$DEPLOY_APP_DIR/"

step "Dépendances, migrations, table de cache, contrôles, redémarrage de Passenger"
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
# Fichier verrouillé avec empreintes (requirements/compile.sh) : --require-hashes refuse
# tout paquet non épinglé ou altéré ; --only-binary interdit toute compilation sur
# l'hébergement (roues manylinux_2_27 au plus pour toutes les dépendances, vérifié en CI
# pour Python 3.12 et 3.13 ; contrôles V02, V04 et V28 de docs/L1-verifications-o2switch.md).
pip install --quiet --require-hashes --only-binary=:all: -r requirements/prod.txt
# Contrôles AVANT toute modification de la base : un avertissement arrête le déploiement
# sans migration appliquée (le DDL n'est pas transactionnel sous MariaDB). Le nouveau code
# est toutefois déjà sur le disque (rsync) : voir deploy/README.md, « Échec en cours de
# déploiement ». Deux commandes distinctes :
# - sécurité (--deploy), SANS --database : avec --database, Django lancerait aussi les
#   contrôles de contraintes des modèles, dont models.W036, que déclenchent les
#   contraintes conditionnelles d'allauth ignorées par MariaDB (plan L1 §3.7) ;
# - base de données seulement (--tag database) : connexion et mode strict (mysql.W002).
python manage.py check --deploy --fail-level WARNING
python manage.py check --database default --tag database --fail-level WARNING
python manage.py migrate --noinput
# Tables du cache partagé (DatabaseCache : gestconf_cache et gestconf_throttle_cache).
# Elles ne sont pas créées par une migration ; la commande est sans effet si elles existent.
python manage.py createcachetable
echo "$release" > RELEASE
# Chemin du venv lu par deploy/cron.sh : le cron charge le même environnement que Passenger.
printf '%s\n' "$venv_activate" > VENV_ACTIVATE
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

# --- 4. Portail pré-rendu (backend de cette version désormais en ligne) ---------------
if [[ "${SKIP_PORTAL:-0}" == "1" ]]; then
  echo "SKIP_PORTAL=1 : portail rendu dans le navigateur jusqu'au prochain --portal-only."
elif [[ -z "${GESTCONF_PRERENDER_API_ORIGIN:-${DEPLOY_BASE_URL:-}}" ]]; then
  echo "Avertissement : DEPLOY_BASE_URL absent, portail non pré-rendu (lancer --portal-only)." >&2
else
  publish_portal
fi

# --- 5. Tests de fumée ---------------------------------------------------------------
if [[ -n "${DEPLOY_BASE_URL:-}" ]]; then
  step "Tests de fumée sur $DEPLOY_BASE_URL"
  "$ROOT/deploy/smoke-test.sh" "$DEPLOY_BASE_URL" "$RELEASE"
fi

step "Déploiement $RELEASE terminé"
