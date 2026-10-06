#!/usr/bin/env bash
# Tests de fumée après déploiement (étude §11.4, étape 7).
# Usage : deploy/smoke-test.sh https://conference.exemple.org [version_attendue]
# Vérifie notamment que les règles de repli SPA n'interceptent pas /api/.

set -uo pipefail

BASE_URL="${1:?Usage : $0 URL_DE_BASE [version_attendue]}"
BASE_URL="${BASE_URL%/}"
EXPECTED_RELEASE="${2:-}"
read -r -a extra_opts <<<"${SMOKE_CURL_OPTS:-}"  # ex. SMOKE_CURL_OPTS="--insecure"
CURL=(curl --silent --show-error --max-time 15 "${extra_opts[@]}")
failures=0

check() {
  local label="$1" ok="$2"
  if [[ "$ok" == "1" ]]; then
    printf '  OK      %s\n' "$label"
  else
    printf '  ÉCHEC   %s\n' "$label"
    failures=$((failures + 1))
  fi
}

status_of() { "${CURL[@]}" -o /dev/null -w '%{http_code}' "$1"; }

# json_has <texte> <clé> <valeur JSON> : tolère les espaces autour de « : ».
json_has() { grep -Eq "\"$2\"[[:space:]]*:[[:space:]]*$3" <<<"$1"; }

# has_meta_csp <html> : CSP à empreintes ajoutée par web/scripts/inject-csp.mjs (balise
# <meta http-equiv="Content-Security-Policy"> portant script-src). Insensible à la casse
# et à l'ordre des attributs. Le dernier grep lit toute son entrée (pas de -q) : avec
# pipefail, une sortie anticipée pourrait faire échouer le grep précédent (SIGPIPE).
has_meta_csp() {
  grep -Eio '<meta[^>]*>' <<<"$1" | grep -Ei 'http-equiv=["'"'"']?content-security-policy' \
    | grep -i 'script-src' >/dev/null
}

# has_header <en-têtes> <nom> <motif ERE de la valeur> : insensible à la casse.
has_header() { grep -Eiq "^$2:[[:space:]]*.*$3" <<<"$1"; }

headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL/")
check "portail : / redirige vers /fr/ (302, lot L2)" \
  "$(grep -Eq '^HTTP/[0-9.]+ 302' <<<"$headers" && has_header "$headers" location '/fr/' && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/fr/")
check "portail : /fr/ renvoie le portail" "$([[ "$body" == *"<portail-root"* ]] && echo 1)"
check "portail : CSP à empreintes en <meta> sur /fr/" "$(has_meta_csp "$body" && echo 1)"

headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL/fr/")
check "portail : en-tête CSP présent" "$(has_header "$headers" content-security-policy 'frame-ancestors' && echo 1)"

# Portail pré-rendu (deploy.sh, E9) : page complète, référencement, plan du site. Un portail
# rendu dans le navigateur (SKIP_PORTAL=1, pas encore de --portal-only) est signalé, pas
# compté en échec.
if [[ "$body" == *'data-gc-rendered="fr:home"'* ]]; then
  check "portail : /fr/ pré-rendue avec adresse canonique et variantes hreflang" \
    "$(grep -Eq '<link[^>]*rel="canonical"[^>]*href="https?://[^"]*/fr/"' <<<"$body" \
      && grep -Eq 'hreflang="en"' <<<"$body" && echo 1)"
  check "portail : Open Graph sur /fr/" "$(grep -Eq 'property="og:title"' <<<"$body" && echo 1)"
  page=$("${CURL[@]}" "$BASE_URL/en/call/")
  check "portail : /en/call/ pré-rendue" "$([[ "$page" == *'data-gc-rendered="en:call"'* ]] && echo 1)"
  sitemap=$("${CURL[@]}" -D - "$BASE_URL/sitemap.xml")
  check "portail : /sitemap.xml (XML, variantes de langue)" \
    "$(has_header "$sitemap" content-type 'xml' && [[ "$sitemap" == *"<urlset"* ]] \
      && [[ "$sitemap" == *'hreflang="en"'* ]] && echo 1)"
  check "portail : robots.txt annonce le plan du site" \
    "$(grep -Eq '^Sitemap:[[:space:]]*https?://.*/sitemap\.xml' <<<"$("${CURL[@]}" "$BASE_URL/robots.txt")" && echo 1)"
else
  printf '  INFO    %s\n' "portail rendu dans le navigateur (non pré-rendu) : lancer deploy.sh --portal-only"
fi

body=$("${CURL[@]}" "$BASE_URL/une-page-qui-n-existe-pas")
check "portail : repli SPA (index.csr.html)" "$([[ "$body" == *"<portail-root"* ]] && echo 1)"
check "portail : CSP en <meta> sur le repli SPA (pages /compte/*)" "$(has_meta_csp "$body" && echo 1)"

robots=$("${CURL[@]}" -D - "$BASE_URL/robots.txt")
check "portail : /robots.txt servi tel quel (texte, pas le repli SPA)" \
  "$(has_header "$robots" content-type 'text/plain' && [[ "$robots" != *"<portail-root"* ]] && echo 1)"
check "portail : robots.txt exclut /api/, /gestion/, /compte/ et /verification" \
  "$(grep -Eq '^Disallow:[[:space:]]*/api/' <<<"$robots" && grep -Eq '^Disallow:[[:space:]]*/gestion/' <<<"$robots" \
    && grep -Eq '^Disallow:[[:space:]]*/compte/' <<<"$robots" \
    && grep -Eq '^Disallow:[[:space:]]*/verification' <<<"$robots" && echo 1)"
# Vérification publique (plan L7, K10) : rendue dans le navigateur, servie par le repli SPA.
body=$("${CURL[@]}" "$BASE_URL/verification/CODEINCONNU")
check "portail : /verification/<code> servie par la coquille rendue dans le navigateur" \
  "$([[ "$body" == *"<portail-root"* ]] && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/gestion/")
check "gestion : /gestion/ servie avec base href /gestion/" "$([[ "$body" == *'<base href="/gestion/"'* ]] && echo 1)"
check "gestion : CSP à empreintes en <meta> sur /gestion/" "$(has_meta_csp "$body" && echo 1)"

headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL/gestion/")
check "gestion : en-tête X-Robots-Tag noindex" "$(has_header "$headers" x-robots-tag 'noindex' && echo 1)"
# Caméra (plan L7, K6) : permise sous /gestion/ pour l'accueil, refusée au portail.
check "gestion : Permissions-Policy camera=(self)" \
  "$(has_header "$headers" permissions-policy 'camera=\(self\)' && echo 1)"
portal_headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL/fr/")
check "portail : Permissions-Policy camera=()" \
  "$(has_header "$portal_headers" permissions-policy 'camera=\(\)' && echo 1)"
manifest=$("${CURL[@]}" -D - "$BASE_URL/gestion/manifest.webmanifest")
check "gestion : manifeste de l'accueil servi (application/manifest+json)" \
  "$(has_header "$manifest" content-type 'manifest\+json' && [[ "$manifest" == *'"start_url"'* ]] && echo 1)"
ngsw=$("${CURL[@]}" -D - -o /dev/null -w '\n%{http_code}' "$BASE_URL/gestion/ngsw.json")
check "gestion : ngsw.json du service worker servi, sans cache long" \
  "$([[ "${ngsw##*$'\n'}" == "200" ]] && ! has_header "$ngsw" cache-control 'immutable' && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/gestion/une/route/profonde")
check "gestion : repli SPA sous /gestion/" "$([[ "$body" == *"<gestion-root"* ]] && echo 1)"

# Une seule requête : en-têtes, corps et code HTTP (dernière ligne).
health=$("${CURL[@]}" -D - -w '\n%{http_code}' "$BASE_URL/api/v1/health")
check "API : /api/v1/health répond 200" "$([[ "${health##*$'\n'}" == "200" ]] && echo 1)"
check "API : health -> base de données OK" "$(json_has "$health" database '"ok"' && echo 1)"
check "API : health -> cache OK (table créée par createcachetable)" "$(json_has "$health" cache '"ok"' && echo 1)"
# File de tâches : le cron run_jobs est passé avec succès récemment (deploy/cron.sh, crontab).
# « unknown » au tout premier déploiement, tant que la crontab n'a pas tourné une fois.
check "API : health -> jobs OK (cron run_jobs actif)" "$(json_has "$health" jobs '"ok"' && echo 1)"
check "API : en-tête X-Robots-Tag noindex sur /api/" "$(has_header "$health" x-robots-tag 'noindex' && echo 1)"
if [[ "$BASE_URL" == https://* ]]; then
  check "API : Django voit la requête en HTTPS (secure=true)" "$(json_has "$health" secure true && echo 1)"
fi
if [[ -n "$EXPECTED_RELEASE" ]]; then
  check "API : version déployée = $EXPECTED_RELEASE" "$(json_has "$health" release "\"$EXPECTED_RELEASE\"" && echo 1)"
fi

# Authentification (allauth headless, client « browser ») : amorçage d'un visiteur anonyme.
# 401 JSON avec meta.is_authenticated=false, et cookie csrftoken posé (lu par Angular).
auth=$("${CURL[@]}" -D - -w '\n%{http_code}' "$BASE_URL/api/_allauth/browser/v1/auth/session")
check "API : auth/session anonyme -> 401 JSON (allauth monté sous /api/_allauth/)" \
  "$([[ "${auth##*$'\n'}" == "401" ]] && json_has "$auth" is_authenticated false && echo 1)"
check "API : auth/session pose le cookie csrftoken" "$(has_header "$auth" set-cookie 'csrftoken=' && echo 1)"
check "API : client « app » d'allauth absent (404)" \
  "$([[ "$(status_of "$BASE_URL/api/_allauth/app/v1/config")" == "404" ]] && echo 1)"

# Édition publique courante (étape L1.5) : 200 si une édition est publiée et désignée
# courante, 404 JSON sinon (premier déploiement) ; jamais le repli SPA ni une erreur 500.
current=$("${CURL[@]}" -w '\n%{http_code}' "$BASE_URL/api/v1/public/editions/current")
check "API : édition publique courante -> 200 ou 404 JSON" \
  "$({ [[ "${current##*$'\n'}" == "200" ]] && json_has "$current" code '"[A-Z]'; } \
    || { [[ "${current##*$'\n'}" == "404" ]] && json_has "$current" code '"not_found"'; } && echo 1)"

# Fichier public (L2.4) : le premier document ou l'affiche publiés, servi par Django
# (jamais par Apache) avec « nosniff ». Sans fichier publié : rien à vérifier.
file_path=$("${CURL[@]}" "$BASE_URL/api/v1/public/portal/site" 2>/dev/null \
  | grep -Eo '"url"[[:space:]]*:[[:space:]]*"/api/v1/public/files/[^"]+"' | head -n 1 \
  | sed -E 's/.*"(\/api\/[^"]+)"$/\1/')
if [[ -n "$file_path" ]]; then
  file_headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL$file_path")
  check "API : fichier public servi (200, nosniff)" \
    "$(grep -Eq '^HTTP/[0-9.]+ 200' <<<"$file_headers" \
      && has_header "$file_headers" x-content-type-options 'nosniff' && echo 1)"
fi
check "API : fichier public inconnu -> 404" \
  "$([[ "$(status_of "$BASE_URL/api/v1/public/files/00000000-0000-0000-0000-000000000000/x.pdf")" == "404" ]] && echo 1)"

body=$("${CURL[@]}" -w '\n%{http_code}' "$BASE_URL/api/v1/route-inexistante")
check "API : URL inconnue -> 404 JSON (non interceptée par le repli SPA)" \
  "$([[ "${body##*$'\n'}" == "404" ]] && json_has "$body" code '"not_found"' && echo 1)"

check "API : pas d'admin Django (/api/admin/ -> 404)" "$([[ "$(status_of "$BASE_URL/api/admin/")" == "404" ]] && echo 1)"

# Diagnostic de l'étape L1.0 (M04, M05) : public, anonyme, sans limite de débit, il expose
# REMOTE_ADDR et les adresses des mandataires. Un GESTCONF_DIAGNOSTICS=1 oublié dans le .env
# après la mesure fait échouer chaque déploiement (M09 automatisé).
check "API : diagnostic désactivé (/api/v1/diagnostics/request -> 404)" \
  "$([[ "$(status_of "$BASE_URL/api/v1/diagnostics/request")" == "404" ]] && echo 1)"

if ((failures > 0)); then
  echo "$failures test(s) de fumée en échec." >&2
  exit 1
fi
echo "Tous les tests de fumée sont passés."
