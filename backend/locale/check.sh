#!/usr/bin/env bash
# Vérifie que les catalogues de traduction versionnés (locale/<langue>/LC_MESSAGES/*.po et
# leurs .mo) sont à jour, SANS modifier l'arbre de travail. Lancé par la CI (job backend) ;
# utilisable en local, depuis backend/, venv actif et gettext installé :
#   locale/check.sh
#
# 1. Chaque .mo versionné correspond à son .po. Le .po est recompilé dans un dossier
#    temporaire (msgfmt --check-format, comme compilemessages), puis les deux .mo sont
#    comparés DÉCOMPILÉS (msgunfmt) : msgunfmt produit une forme textuelle normalisée
#    (entrées triées par msgid). Une comparaison octet par octet, elle, dépendrait de la
#    version de msgfmt (table de hachage, en-tête), et pourrait échouer à tort quand la
#    CI et le poste de développement n'ont pas la même version de gettext.
# 2. Chaque .po correspond au code. makemessages est lancé sur une COPIE du backend, puis
#    msgattrib vérifie qu'il ne reste aucune entrée non traduite (message ajouté au code),
#    approximative (« fuzzy » : message modifié) ou obsolète (message retiré du code). Les
#    .po ne sont pas comparés au caractère près : la coupure des lignes, les commentaires
#    de position et l'en-tête dépendent de la version de xgettext.
set -euo pipefail

cd "$(dirname "$0")/.."

for tool in msgfmt msgunfmt msgattrib msgmerge msguniq xgettext; do
  if ! command -v "$tool" >/dev/null; then
    echo "Erreur : $tool introuvable (installer gettext)." >&2
    exit 2
  fi
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
errors=0

fail() {
  echo "ÉCHEC : $*" >&2
  errors=$((errors + 1))
}

mapfile -t po_files < <(find locale -path '*/LC_MESSAGES/*.po' -type f | sort)
if ((${#po_files[@]} == 0)); then
  echo "Erreur : aucun catalogue .po sous locale/." >&2
  exit 2
fi

# --- 1. Les .mo versionnés correspondent aux .po -------------------------------------
for po in "${po_files[@]}"; do
  mo="${po%.po}.mo"
  if [[ ! -f "$mo" ]]; then
    fail "$mo absent : lancer « python manage.py compilemessages -l <langue> --ignore=.venv »."
    continue
  fi
  msgfmt --check-format -o "$work/fresh.mo" "$po"
  if ! diff -u <(msgunfmt "$mo") <(msgunfmt "$work/fresh.mo") >"$work/mo.diff"; then
    fail "$mo ne correspond pas à $po : lancer « python manage.py compilemessages -l <langue> --ignore=.venv »."
    cat "$work/mo.diff" >&2
  fi
done
while IFS= read -r mo; do
  [[ -f "${mo%.mo}.po" ]] || fail "$mo n'a pas de .po source."
done < <(find locale -path '*/LC_MESSAGES/*.mo' -type f | sort)

# --- 2. Les .po correspondent au code ------------------------------------------------
# Copie sans les dossiers cachés (.venv, caches) ni __pycache__ : makemessages les ignore
# de toute façon (motif « .* » par défaut).
copy="$work/backend"
mkdir "$copy"
tar --exclude='./.*' --exclude='__pycache__' -cf - . | tar -xf - -C "$copy"

for po in "${po_files[@]}"; do
  language="$(basename "$(dirname "$(dirname "$po")")")"
  domain="$(basename "$po" .po)"
  (cd "$copy" && python manage.py makemessages --locale "$language" --domain "$domain" \
    --add-location=file --verbosity 0)
  regenerated="$copy/$po"
  for kind in untranslated only-fuzzy only-obsolete; do
    case "$kind" in
      untranslated) options=(--untranslated --no-obsolete) label="non traduites (messages ajoutés au code)" ;;
      only-fuzzy) options=(--only-fuzzy --no-obsolete) label="approximatives (messages modifiés dans le code)" ;;
      only-obsolete) options=(--only-obsolete) label="obsolètes (messages retirés du code)" ;;
    esac
    entries="$(msgattrib "${options[@]}" "$regenerated")"
    if [[ -n "$entries" ]]; then
      fail "$po : entrées $label. Lancer « python manage.py makemessages -l $language --add-location=file », traduire, puis compilemessages."
      printf '%s\n' "$entries" >&2
    fi
  done
done

if ((errors > 0)); then
  echo "$errors erreur(s) dans les catalogues de traduction." >&2
  exit 1
fi
echo "Catalogues de traduction à jour (${#po_files[@]} .po et leurs .mo)."
