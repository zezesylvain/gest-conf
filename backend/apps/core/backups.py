"""Sauvegarde et restauration de la base et des fichiers (plan L9, S2 et S3 ; étude §11.6).

**Sauvegarde** (``manage.py backup_db``, cron quotidien) :

- dump MariaDB par ``mariadb-dump`` (ou ``mysqldump``), identifiants dans un fichier
  d'options temporaire en 0600, **jamais sur la ligne de commande** (visible par ``ps``) ;
- ``--single-transaction`` (instantané cohérent d'InnoDB, sans verrou), ``--quick`` (ligne à
  ligne), ``--hex-blob``, ``--no-tablespaces`` (aucun privilège global, hébergement
  mutualisé), en ``utf8mb4`` ;
- tables du cache exclues (recréées par ``createcachetable``) ; sessions sauvegardées **sans
  leurs lignes** : une session est un titre d'accès, une sauvegarde volée n'en livre aucune ;
- compression en flux, écriture sous un nom temporaire puis renommage ; dump complet vérifié
  (ligne finale ``-- Dump completed``) ;
- **manifeste** JSON à côté : date, version, dernière migration de chaque application,
  taille et empreinte SHA-256 du dump, inventaire des fichiers déposés (chemin relatif,
  taille) pour vérifier la complétude d'une copie ou d'une restauration ;
- rotation : 7 quotidiennes, 4 hebdomadaires, 3 mensuelles.

Les fichiers déposés ne sont **pas** recopiés sur le même disque (cela ne protège pas d'une
perte de l'hébergement) : ils sont rapatriés avec les dumps (``deploy/pull-backups.sh``).

**Restauration** (``manage.py restore_db``) : dans une base **vide** seulement, après
vérification de l'empreinte du dump ; fichiers recopiés dans des dossiers vides, puis
comparés au manifeste.

SQLite (développement) : dump SQL par ``iterdump()`` ; pas de restauration.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

MANIFEST_FORMAT = 1
BACKUP_PREFIX = "gestconf-"
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
BACKUP_NAME = re.compile(r"^gestconf-(\d{8}T\d{6}Z)\.sql\.gz$")
DUMP_COMPLETED = b"-- Dump completed"
CHUNK_SIZE = 1024 * 1024
# Tables sauvegardées sans leurs lignes (structure seule) : titres d'accès.
STRUCTURE_ONLY_TABLES = ("django_session",)
STDERR_MAX_LENGTH = 500


class BackupError(Exception):
    """Sauvegarde ou restauration impossible ; le message est destiné à l'opérateur."""


@dataclass(frozen=True)
class BackupResult:
    dump: Path
    manifest: Path
    removed: list[Path] = field(default_factory=list)


@dataclass
class RestoreReport:
    dump: Path
    created_at: str
    missing_files: list[str] = field(default_factory=list)
    size_mismatches: list[str] = field(default_factory=list)
    pending_migrations: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (self.missing_files or self.size_mismatches)


# --- Emplacements et outils ------------------------------------------------------------------


def backup_dir() -> Path:
    """Dossier des sauvegardes, créé en 0700 (hors racine web)."""
    path = Path(settings.GESTCONF_BACKUP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def file_roots() -> dict[str, Path]:
    """Dossiers de fichiers déposés à inventorier, par nom stable (clé du manifeste).

    ``private`` n'apparaît que s'il est hors de ``GESTCONF_FILES_DIR`` (par défaut, il en
    est un sous-dossier, inventorié avec lui).
    """
    files = Path(settings.GESTCONF_FILES_DIR)
    private = Path(settings.GESTCONF_PRIVATE_FILES_DIR)
    roots = {"files": files}
    if not private.resolve().is_relative_to(files.resolve()):
        roots["private"] = private
    return roots


def find_tool(*names: str) -> str:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    raise BackupError(
        f"Outil introuvable : {', '.join(names)} (contrôle V18 de la fiche o2switch)."
    )


def is_mariadb_tool(executable: str) -> bool:
    """``mysqldump`` de MySQL 8 interroge ``COLUMN_STATISTICS``, absente de MariaDB."""
    result = subprocess.run(  # noqa: S603 (exécutable résolu par shutil.which, sans shell)
        [executable, "--version"], capture_output=True, text=True, check=False, timeout=30
    )
    return "mariadb" in (result.stdout + result.stderr).lower()


def cache_tables() -> list[str]:
    return sorted(
        {
            config["LOCATION"]
            for config in settings.CACHES.values()
            if config["BACKEND"].endswith("DatabaseCache")
        }
    )


def _option_value(value: Any) -> str:
    """Valeur d'un fichier d'options MariaDB, entre guillemets (dièses, espaces…)."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


@contextmanager
def option_file(database: dict[str, Any], directory: Path) -> Iterator[Path]:
    """Fichier ``[client]`` temporaire en 0600, effacé à la sortie, même en cas d'erreur."""
    descriptor, name = tempfile.mkstemp(prefix=".client-", suffix=".cnf", dir=directory)
    path = Path(name)
    try:
        os.fchmod(descriptor, 0o600)
        lines = ["[client]"]
        host = str(database.get("HOST") or "")
        values = {
            "user": database.get("USER"),
            "password": database.get("PASSWORD"),
            "socket" if host.startswith("/") else "host": host,
            "port": database.get("PORT"),
        }
        lines += [f"{key}={_option_value(value)}" for key, value in values.items() if value]
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        yield path
    finally:
        path.unlink(missing_ok=True)


# --- Rotation ----------------------------------------------------------------------------------


def backups_to_keep(
    stamps: Iterable[datetime], *, daily: int, weekly: int, monthly: int
) -> set[datetime]:
    """Rotation grand-père, père, fils : la plus récente de chacun des derniers jours,
    semaines (ISO) et mois. Une sauvegarde peut compter à plusieurs titres."""
    ordered = sorted(set(stamps), reverse=True)
    keep: set[datetime] = set()
    periods = (
        (daily, lambda stamp: stamp.date()),
        (weekly, lambda stamp: stamp.isocalendar()[:2]),
        (monthly, lambda stamp: (stamp.year, stamp.month)),
    )
    for count, period in periods:
        seen: list[Any] = []
        for stamp in ordered:
            if len(seen) >= count:
                break
            key = period(stamp)
            if key not in seen:
                seen.append(key)
                keep.add(stamp)
    return keep


def existing_backups(directory: Path) -> dict[datetime, list[Path]]:
    """Sauvegardes présentes (dump et manifeste), par date ; les autres fichiers sont ignorés."""
    found: dict[datetime, list[Path]] = {}
    for path in directory.iterdir():
        match = BACKUP_NAME.match(path.name)
        if not match:
            continue
        stamp = datetime.strptime(match.group(1), STAMP_FORMAT).replace(tzinfo=UTC)
        found.setdefault(stamp, []).append(path)
        manifest = manifest_path(path)
        if manifest.exists():
            found[stamp].append(manifest)
    return found


def rotate(directory: Path) -> list[Path]:
    """Supprime les sauvegardes hors rotation et les restes d'une exécution interrompue."""
    removed: list[Path] = []
    for leftover in directory.glob(f"{BACKUP_PREFIX}*.part"):
        leftover.unlink(missing_ok=True)
        removed.append(leftover)
    found = existing_backups(directory)
    keep = backups_to_keep(
        found,
        daily=settings.GESTCONF_BACKUP_KEEP_DAILY,
        weekly=settings.GESTCONF_BACKUP_KEEP_WEEKLY,
        monthly=settings.GESTCONF_BACKUP_KEEP_MONTHLY,
    )
    for stamp, paths in found.items():
        if stamp in keep:
            continue
        for path in paths:
            path.unlink(missing_ok=True)
            removed.append(path)
    return removed


# --- Sauvegarde -------------------------------------------------------------------------------


def manifest_path(dump: Path) -> Path:
    return dump.with_name(dump.name.split(".", 1)[0] + ".json")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_inventory(roots: dict[str, Path]) -> dict[str, Any]:
    """Inventaire des fichiers déposés : ``[chemin relatif, taille]`` par racine."""
    entries: dict[str, list[list[Any]]] = {}
    count = total = 0
    for key, root in roots.items():
        items: list[list[Any]] = []
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
                items.append([path.relative_to(root).as_posix(), size])
                count += 1
                total += size
        entries[key] = items
    return {"count": count, "bytes": total, "roots": entries}


def applied_migrations(alias: str = DEFAULT_DB_ALIAS) -> dict[str, str]:
    """Dernière migration appliquée de chaque application (numérotation à zéros en tête)."""
    latest: dict[str, str] = {}
    for app, name in MigrationRecorder(connections[alias]).applied_migrations():
        if name > latest.get(app, ""):
            latest[app] = name
    return dict(sorted(latest.items()))


def _run_dump(arguments: list[str], output: gzip.GzipFile) -> None:
    """Lance un dump et en recopie la sortie dans ``output`` ; vérifie qu'il est complet."""
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(  # noqa: S603 (outil résolu par shutil.which, sans shell)
            arguments, stdout=subprocess.PIPE, stderr=errors
        )
        if process.stdout is None:  # pragma: no cover (stdout=PIPE)
            raise BackupError("Sortie du dump illisible.")
        tail = b""
        for chunk in iter(lambda: process.stdout.read(CHUNK_SIZE), b""):
            output.write(chunk)
            tail = (tail + chunk)[-4096:]
        process.stdout.close()
        returncode = process.wait()
        if returncode != 0:
            errors.seek(0)
            message = errors.read().decode("utf-8", "replace").strip()[:STDERR_MAX_LENGTH]
            raise BackupError(f"Le dump a échoué (code {returncode}) : {message}")
    if DUMP_COMPLETED not in tail:
        raise BackupError("Dump incomplet : la ligne finale « -- Dump completed » manque.")


def dump_mariadb(database: dict[str, Any], destination: Path, directory: Path) -> list[str]:
    """Dump compressé de la base ; renvoie les tables exclues ou réduites à leur structure."""
    tool = find_tool("mariadb-dump", "mysqldump")
    common = [
        "--single-transaction",
        "--quick",
        "--hex-blob",
        "--no-tablespaces",
        "--skip-lock-tables",
        "--default-character-set=utf8mb4",
    ]
    if not is_mariadb_tool(tool):
        common.append("--column-statistics=0")
    name = database["NAME"]
    skipped = [*cache_tables(), *STRUCTURE_ONLY_TABLES]
    with option_file(database, directory) as options:
        defaults = f"--defaults-extra-file={options}"  # toujours la première option
        with gzip.open(destination, "wb", compresslevel=6) as output:
            _run_dump(
                [tool, defaults, *common, *(f"--ignore-table={name}.{t}" for t in skipped), name],
                output,
            )
            # Structure seule des sessions : la table existe après restauration, vide.
            _run_dump([tool, defaults, *common, "--no-data", name, *STRUCTURE_ONLY_TABLES], output)
    return skipped


def dump_sqlite(alias: str, destination: Path) -> None:
    """Dump SQL de la base SQLite (développement). ``iterdump()`` lit par la connexion
    courante : l'API ``backup()`` attendrait sans fin le verrou d'une transaction ouverte
    sur une base en mémoire à cache partagé (base des tests)."""
    connection = connections[alias]
    connection.ensure_connection()
    with gzip.open(destination, "wt", encoding="utf-8") as output:
        for statement in connection.connection.iterdump():
            output.write(f"{statement}\n")


def backup(*, alias: str = DEFAULT_DB_ALIAS, now: datetime | None = None) -> BackupResult:
    """Sauvegarde complète : dump, manifeste, puis rotation."""
    directory = backup_dir()
    now = now or timezone.now()
    stamp = now.astimezone(UTC).strftime(STAMP_FORMAT)
    database = connections[alias].settings_dict
    vendor = connections[alias].vendor
    dump = directory / f"{BACKUP_PREFIX}{stamp}.sql.gz"
    if vendor not in ("mysql", "sqlite"):
        raise BackupError(f"Moteur de base non pris en charge : {vendor}.")
    if dump.exists():
        raise BackupError(f"Une sauvegarde de même date existe déjà : {dump.name}.")
    partial = dump.with_name(dump.name + ".part")
    try:
        skipped: list[str] = []
        if vendor == "mysql":
            skipped = dump_mariadb(database, partial, directory)
        else:
            dump_sqlite(alias, partial)
        partial.chmod(0o600)
        partial.replace(dump)
    finally:
        partial.unlink(missing_ok=True)
    manifest = {
        "format": MANIFEST_FORMAT,
        "created_at": now.astimezone(UTC).isoformat(),
        "release": settings.GESTCONF_RELEASE,
        "database": {
            "engine": vendor,
            "file": dump.name,
            "bytes": dump.stat().st_size,
            "sha256": sha256_of(dump),
            "skipped_tables": skipped,
        },
        "migrations": applied_migrations(alias),
        "files": file_inventory(file_roots()),
    }
    target = manifest_path(dump)
    partial_manifest = target.with_name(target.name + ".part")
    partial_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    partial_manifest.chmod(0o600)
    partial_manifest.replace(target)
    return BackupResult(dump=dump, manifest=target, removed=rotate(directory))


def latest_backup_success() -> datetime | None:
    """Dernière sauvegarde réussie, d'après le battement de cœur de ``backup_db``."""
    from apps.core.models import CronHeartbeat

    return (
        CronHeartbeat.objects.filter(name="backup_db")
        .values_list("last_success_at", flat=True)
        .first()
    )


# --- Restauration -----------------------------------------------------------------------------


def read_manifest(dump: Path) -> dict[str, Any]:
    path = manifest_path(dump)
    if not path.is_file():
        raise BackupError(f"Manifeste absent : {path.name}.")
    manifest = json.loads(path.read_text("utf-8"))
    if manifest.get("format") != MANIFEST_FORMAT:
        raise BackupError("Format de manifeste inconnu.")
    if sha256_of(dump) != manifest["database"]["sha256"]:
        raise BackupError("Empreinte du dump différente de celle du manifeste : copie altérée.")
    return manifest


def target_table_count(database: dict[str, Any]) -> int:
    import pymysql

    connection = pymysql.connect(
        host=database.get("HOST") or "localhost",
        port=int(database.get("PORT") or 3306),
        user=database.get("USER"),
        password=database.get("PASSWORD") or "",
        charset="utf8mb4",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                [database["NAME"]],
            )
            return int(cursor.fetchone()[0])
    finally:
        connection.close()


def load_mariadb(dump: Path, database: dict[str, Any], directory: Path) -> None:
    """Charge un dump compressé dans une base **vide** (refus sinon)."""
    if target_table_count(database):
        raise BackupError(
            f"La base cible « {database['NAME']} » n'est pas vide : restaurer dans une base neuve."
        )
    client = find_tool("mariadb", "mysql")
    with option_file(database, directory) as options, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(  # noqa: S603 (outil résolu par shutil.which, sans shell)
            [
                client,
                f"--defaults-extra-file={options}",
                "--default-character-set=utf8mb4",
                database["NAME"],
            ],
            stdin=subprocess.PIPE,
            stderr=errors,
        )
        if process.stdin is None:  # pragma: no cover (stdin=PIPE)
            raise BackupError("Entrée du client illisible.")
        try:
            with gzip.open(dump, "rb") as source:
                for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
                    process.stdin.write(chunk)
        finally:
            process.stdin.close()
        returncode = process.wait()
        if returncode != 0:
            errors.seek(0)
            message = errors.read().decode("utf-8", "replace").strip()[:STDERR_MAX_LENGTH]
            raise BackupError(f"Chargement du dump en échec (code {returncode}) : {message}")


def copy_files(source: Path, roots: dict[str, Path]) -> None:
    """Recopie les fichiers rapatriés (``<source>/<racine>/…``) dans des dossiers vides."""
    for key, target in roots.items():
        origin = source / key
        if not origin.is_dir():
            raise BackupError(f"Dossier « {key} » absent de la copie.")
        if target.exists() and any(target.iterdir()):
            raise BackupError(f"Le dossier de fichiers « {target} » n'est pas vide.")
        shutil.copytree(origin, target, dirs_exist_ok=True)


def verify_files(manifest: dict[str, Any], roots: dict[str, Path], report: RestoreReport) -> None:
    for key, entries in manifest["files"]["roots"].items():
        root = roots.get(key)
        for relative, size in entries:
            path = root / relative if root else None
            if path is None or not path.is_file():
                report.missing_files.append(f"{key}/{relative}")
            elif path.stat().st_size != size:
                report.size_mismatches.append(f"{key}/{relative}")


def pending_migrations(alias: str = DEFAULT_DB_ALIAS) -> list[str]:
    """Migrations du code non appliquées à la base restaurée (dump plus ancien que le code)."""
    executor = MigrationExecutor(connections[alias])
    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    return [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]


def restore(
    dump: Path, *, files_from: Path | None = None, alias: str = DEFAULT_DB_ALIAS
) -> RestoreReport:
    """Restauration complète dans une base et des dossiers **vides** ; rapport de complétude.

    Les migrations en attente sont signalées, jamais appliquées d'office : restaurer un dump
    plus ancien que le code est une décision de l'opérateur (redéployer l'ancien commit, ou
    migrer en connaissance de cause).
    """
    manifest = read_manifest(dump)
    connection = connections[alias]
    if connection.vendor != "mysql" or manifest["database"]["engine"] != "mysql":
        raise BackupError("La restauration n'est prise en charge que pour MariaDB.")
    connection.close()
    load_mariadb(dump, connection.settings_dict, backup_dir())
    roots = file_roots()
    if files_from is not None:
        copy_files(files_from, roots)
    report = RestoreReport(dump=dump, created_at=manifest["created_at"])
    verify_files(manifest, roots, report)
    call_command("createcachetable", database=alias, verbosity=0)
    report.pending_migrations = pending_migrations(alias)
    return report
