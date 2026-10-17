#!/usr/bin/env bash
# Copie hors hébergement des sauvegardes et des fichiers déposés (plan L9, S3 ; étude §11.6).
#
# À lancer depuis le POSTE ou le SERVEUR DE L'OPÉRATEUR, jamais depuis l'hébergement, par
# son propre cron, avec l'accès SSH au compte o2switch. Rien n'est poussé vers un tiers :
# aucune clé de stockage externe n'est déposée sur le serveur.
#
#   PULL_SSH=compte@serveur PULL_DEST=/srv/gestconf-copies deploy/pull-backups.sh
#
# Heure conseillée : après backup_db (2 h 07) et AVANT cleanup (3 h 17), par exemple 2 h 40 :
# un fichier purgé par cleanup après la sauvegarde manquerait sinon à la vérification.
#
# - dumps et manifestes : copiés, jamais supprimés par la copie (pas de --delete) ;
# - fichiers déposés : un instantané daté par passage, les fichiers inchangés en liens
#   physiques vers l'instantané précédent (--link-dest) : un effacement ou un chiffrement
#   malveillant sur l'hébergement n'atteint pas les copies déjà prises ;
# - conservation locale : PULL_KEEP_DAYS jours (dumps et instantanés), le dernier toujours ;
# - vérification : empreinte du dernier dump, puis chaque fichier de son manifeste présent
#   dans l'instantané avec sa taille (python3). Code de sortie non nul sinon.
#
# Variables :
#   PULL_SSH          compte@serveur (obligatoire)
#   PULL_DEST         dossier local des copies (obligatoire), créé en 0700
#   PULL_APP_DIR      dossier distant de l'application (défaut : gestconf-app)
#   PULL_BACKUP_DIR   dossier distant des sauvegardes (défaut : <PULL_APP_DIR>/var/backups)
#   PULL_FILES_DIR    dossier distant des fichiers (défaut : <PULL_APP_DIR>/var/files)
#   PULL_PRIVATE_DIR  dossier distant des fichiers privés, s'il est hors de PULL_FILES_DIR
#   PULL_KEEP_DAYS    conservation locale en jours (défaut : 30)
#
# Restauration à partir de ces copies : deploy/restore.sh <dump> <instantané>.
set -euo pipefail

: "${PULL_SSH:?Définir PULL_SSH (compte@serveur)}"
: "${PULL_DEST:?Définir PULL_DEST (dossier local des copies)}"
PULL_APP_DIR="${PULL_APP_DIR:-gestconf-app}"
PULL_BACKUP_DIR="${PULL_BACKUP_DIR:-$PULL_APP_DIR/var/backups}"
PULL_FILES_DIR="${PULL_FILES_DIR:-$PULL_APP_DIR/var/files}"
PULL_PRIVATE_DIR="${PULL_PRIVATE_DIR:-}"
PULL_KEEP_DAYS="${PULL_KEEP_DAYS:-30}"

umask 077
mkdir -p "$PULL_DEST/backups" "$PULL_DEST/files"
chmod 700 "$PULL_DEST"

step() { printf '\n==> %s\n' "$*"; }

step "Dumps et manifestes ($PULL_SSH:$PULL_BACKUP_DIR)"
rsync -a --partial \
  --include 'gestconf-*.sql.gz' --include 'gestconf-*.json' --exclude '*' \
  "$PULL_SSH:$PULL_BACKUP_DIR/" "$PULL_DEST/backups/"

stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
snapshot="$PULL_DEST/files/$stamp"
partial="$snapshot.part"
rm -rf "$partial"
mkdir -p "$partial"

pull_tree() {
  local remote="$1" name="$2"
  local link=()
  # Installation neuve : aucun fichier encore déposé, le dossier distant n'existe pas. On
  # garde un dossier vide dans l'instantané (restore.sh attend files/), sans échouer.
  # shellcheck disable=SC2029  # chemin distant développé côté poste, à dessein
  if ! ssh "${PULL_SSH}" "test -d '$remote'"; then
    printf 'Dossier distant absent (%s) : instantané vide pour %s.\n' "$remote" "$name"
    mkdir -p "$partial/$name"
    return
  fi
  if [[ -d "$PULL_DEST/files/latest/$name" ]]; then
    link=(--link-dest="$(cd "$PULL_DEST/files/latest/$name" && pwd -P)")
  fi
  rsync -a --partial "${link[@]}" "$PULL_SSH:$remote/" "$partial/$name/"
}

step "Fichiers déposés ($PULL_SSH:$PULL_FILES_DIR), instantané $stamp"
pull_tree "$PULL_FILES_DIR" files
if [[ -n "$PULL_PRIVATE_DIR" ]]; then
  pull_tree "$PULL_PRIVATE_DIR" private
fi
mv "$partial" "$snapshot"
ln -sfn "$stamp" "$PULL_DEST/files/latest"

step "Conservation locale : $PULL_KEEP_DAYS jours"
find "$PULL_DEST/backups" -maxdepth 1 -type f -name 'gestconf-*' -mtime +"$PULL_KEEP_DAYS" -delete
latest_target="$(readlink "$PULL_DEST/files/latest")"
while IFS= read -r old; do
  if [[ "$(basename "$old")" != "$latest_target" ]]; then
    rm -rf "$old"
  fi
done < <(find "$PULL_DEST/files" -mindepth 1 -maxdepth 1 -type d -name '2*Z' -mtime +"$PULL_KEEP_DAYS")

step "Vérification du dernier dump et de l'instantané"
python3 - "$PULL_DEST/backups" "$snapshot" <<'PY'
import hashlib
import json
import pathlib
import sys

backups, snapshot = (pathlib.Path(arg) for arg in sys.argv[1:3])
manifests = sorted(backups.glob("gestconf-*.json"))
if not manifests:
    sys.exit("Aucun manifeste rapatrié : backup_db a-t-il tourné ?")
manifest = json.loads(manifests[-1].read_text("utf-8"))
dump = backups / manifest["database"]["file"]
digest = hashlib.sha256()
with dump.open("rb") as handle:
    for chunk in iter(lambda: handle.read(1 << 20), b""):
        digest.update(chunk)
if digest.hexdigest() != manifest["database"]["sha256"]:
    sys.exit(f"Empreinte différente de celle du manifeste : {dump.name}")
problems = []
for root, entries in manifest["files"]["roots"].items():
    for relative, size in entries:
        path = snapshot / root / relative
        if not path.is_file():
            problems.append(f"absent : {root}/{relative}")
        elif path.stat().st_size != size:
            problems.append(f"taille différente : {root}/{relative}")
print(f"{dump.name} : empreinte conforme ; {manifest['files']['count']} fichiers au manifeste.")
if problems:
    print("\n".join(problems[:20]))
    sys.exit(f"{len(problems)} fichier(s) non conforme(s) dans l'instantané.")
print("Instantané conforme au manifeste.")
PY
