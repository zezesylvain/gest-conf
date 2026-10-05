#!/usr/bin/env bash
# Recompile les fichiers verrouillés (*.txt, avec empreintes SHA-256) à partir des
# fichiers sources (*.in), avec pip-tools (installé par requirements/dev.txt).
#
# À lancer depuis backend/, dans le venv Python 3.12 :
#   requirements/compile.sh                            # sans monter de version
#   requirements/compile.sh --upgrade-package django   # options transmises à pip-compile
#
# Ordre imposé : base.txt d'abord, car prod.in et dev.in s'y contraignent (-c base.txt),
# ce qui garantit les mêmes versions d'exécution en développement et en production.
# Le résultat doit aussi s'installer sous Python 3.13 (la CI teste les deux).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    echo "Erreur : compiler avec Python 3.12 (venv backend/.venv)." >&2
    exit 1
fi

export CUSTOM_COMPILE_COMMAND="requirements/compile.sh"
options=(--quiet --generate-hashes --strip-extras --allow-unsafe "$@")

for name in base prod dev; do
    pip-compile "${options[@]}" --output-file "requirements/${name}.txt" "requirements/${name}.in"
done
