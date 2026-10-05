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

body=$("${CURL[@]}" "$BASE_URL/")
check "portail : / renvoie la page pré-rendue" "$([[ "$body" == *"<portail-root"* && "$body" == *"<h1"* ]] && echo 1)"

headers=$("${CURL[@]}" -D - -o /dev/null "$BASE_URL/")
check "portail : en-tête CSP présent" "$(grep -qi '^content-security-policy:.*frame-ancestors' <<<"$headers" && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/une-page-qui-n-existe-pas")
check "portail : repli SPA (index.csr.html)" "$([[ "$body" == *"<portail-root"* ]] && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/gestion/")
check "gestion : /gestion/ servie avec base href /gestion/" "$([[ "$body" == *'<base href="/gestion/"'* ]] && echo 1)"

body=$("${CURL[@]}" "$BASE_URL/gestion/une/route/profonde")
check "gestion : repli SPA sous /gestion/" "$([[ "$body" == *"<gestion-root"* ]] && echo 1)"

health=$("${CURL[@]}" -w '\n%{http_code}' "$BASE_URL/api/v1/health")
check "API : /api/v1/health répond 200 et base OK" \
  "$([[ "${health##*$'\n'}" == "200" ]] && json_has "$health" database '"ok"' && echo 1)"
if [[ "$BASE_URL" == https://* ]]; then
  check "API : Django voit la requête en HTTPS (secure=true)" "$(json_has "$health" secure true && echo 1)"
fi
if [[ -n "$EXPECTED_RELEASE" ]]; then
  check "API : version déployée = $EXPECTED_RELEASE" "$(json_has "$health" release "\"$EXPECTED_RELEASE\"" && echo 1)"
fi

body=$("${CURL[@]}" -w '\n%{http_code}' "$BASE_URL/api/v1/route-inexistante")
check "API : URL inconnue -> 404 JSON (non interceptée par le repli SPA)" \
  "$([[ "${body##*$'\n'}" == "404" ]] && json_has "$body" code '"not_found"' && echo 1)"

check "API : pas d'admin Django (/api/admin/ -> 404)" "$([[ "$(status_of "$BASE_URL/api/admin/")" == "404" ]] && echo 1)"

if ((failures > 0)); then
  echo "$failures test(s) de fumée en échec." >&2
  exit 1
fi
echo "Tous les tests de fumée sont passés."
