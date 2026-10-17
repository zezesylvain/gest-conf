"""Sauvegarde et restauration (plan L9, S2 et S3 ; étude §11.6)."""

from __future__ import annotations

import gzip
import io
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, connections

from apps.core import backups
from apps.core.locking import command_lock
from apps.core.models import AuditLog, CronHeartbeat, HeartbeatStatus

pytestmark = pytest.mark.django_db

SQLITE_ONLY = pytest.mark.skipif(
    connection.vendor != "sqlite", reason="copie SQLite ; MariaDB : voir les tests mariadb_only"
)


@pytest.fixture
def backup_settings(settings, tmp_path):
    settings.GESTCONF_BACKUP_DIR = tmp_path / "backups"
    settings.GESTCONF_FILES_DIR = tmp_path / "files"
    settings.GESTCONF_PRIVATE_FILES_DIR = tmp_path / "files" / "private"
    (tmp_path / "files" / "private" / "submissions").mkdir(parents=True)
    (tmp_path / "files" / "private" / "submissions" / "a.pdf").write_bytes(b"%PDF-1.7 a")
    (tmp_path / "files" / "public").mkdir()
    (tmp_path / "files" / "public" / "logo.png").write_bytes(b"png")
    return settings


def stamp(day: str) -> datetime:
    return datetime.fromisoformat(day).replace(tzinfo=UTC)


def test_s2_rotation_keeps_7_daily_4_weekly_3_monthly():
    """Rotation grand-père, père, fils : la plus récente de chaque jour, semaine, mois."""
    start = stamp("2026-10-12T02:00:00")
    stamps = [start - timedelta(days=offset) for offset in range(120)]
    stamps.append(start - timedelta(hours=1))  # deux sauvegardes le même jour
    keep = backups.backups_to_keep(stamps, daily=7, weekly=4, monthly=3)
    days = sorted({kept.date().isoformat() for kept in keep}, reverse=True)
    assert len(keep) == len(days)  # une seule par jour gardé, la plus récente
    assert start in keep and start - timedelta(hours=1) not in keep
    assert days[:7] == [(start - timedelta(days=n)).date().isoformat() for n in range(7)]
    # Dimanches des semaines ISO précédentes, puis derniers jours des mois précédents.
    # Semaines ISO : la courante, puis les dimanches des trois précédentes ; mois : la
    # plus récente d'octobre, puis les derniers jours de septembre et d'août.
    assert {"2026-10-11", "2026-10-04", "2026-09-27"} <= set(days)
    assert "2026-09-20" not in days
    assert {"2026-09-30", "2026-08-31"} <= set(days)
    assert len(keep) == 11


def test_s2_rotate_removes_only_backups_out_of_rotation_and_leftovers(backup_settings, tmp_path):
    directory = tmp_path / "rotation"
    directory.mkdir()
    start = stamp("2026-10-12T02:00:00")
    for offset in range(40):
        name = (start - timedelta(days=offset)).strftime(backups.STAMP_FORMAT)
        (directory / f"gestconf-{name}.sql.gz").write_bytes(b"x")
        (directory / f"gestconf-{name}.json").write_text("{}")
    (directory / "gestconf-20261012T030000Z.sql.gz.part").write_bytes(b"interrompu")
    (directory / "notes.txt").write_text("à garder")
    removed = backups.rotate(directory)
    remaining = {path.name for path in directory.iterdir()}
    assert "notes.txt" in remaining
    assert not any(name.endswith(".part") for name in remaining)
    dumps = [name for name in remaining if name.endswith(".sql.gz")]
    assert len(dumps) == len([name for name in remaining if name.endswith(".json")])
    assert 7 <= len(dumps) <= 14
    assert len(removed) == 40 * 2 + 1 - 2 * len(dumps)


def test_s2_option_file_is_private_quoted_and_removed(tmp_path):
    database = {"USER": "gc", "PASSWORD": 'p#ss "w\\d', "HOST": "127.0.0.1", "PORT": 3306}
    with backups.option_file(database, tmp_path) as path:
        assert path.stat().st_mode & 0o777 == 0o600
        text = path.read_text()
        assert text.startswith("[client]\n")
        assert 'password="p#ss \\"w\\\\d"' in text
        assert 'host="127.0.0.1"' in text and 'port="3306"' in text
    assert not path.exists()
    with backups.option_file({"USER": "gc", "HOST": "/run/mysqld.sock"}, tmp_path) as path:
        assert 'socket="/run/mysqld.sock"' in path.read_text()


class FakeDump:
    """Remplace ``subprocess.Popen`` : enregistre les arguments, produit un dump factice."""

    def __init__(self, output: bytes = b"CREATE TABLE t;\n-- Dump completed on 2026\n", code=0):
        self.calls: list[list[str]] = []
        self.output = output
        self.code = code

    def __call__(self, arguments, stdout=None, stderr=None, **kwargs):
        self.calls.append(list(arguments))
        options = arguments[1].split("=", 1)[1]
        self.option_text = Path(options).read_text()
        if stderr is not None:
            stderr.write(b"erreur simulee")
        fake = self

        class Process:
            stdout = io.BytesIO(fake.output)

            def wait(self):
                return fake.code

        return Process()


@pytest.fixture
def fake_mariadb(monkeypatch):
    fake = FakeDump()
    monkeypatch.setattr(backups, "find_tool", lambda *names: f"/usr/bin/{names[0]}")
    monkeypatch.setattr(backups, "is_mariadb_tool", lambda tool: True)
    monkeypatch.setattr(subprocess, "Popen", fake)
    return fake


def test_s2_dump_keeps_password_off_the_command_line_and_skips_sessions(
    fake_mariadb, backup_settings, tmp_path
):
    """Identifiants dans le fichier d'options seulement ; caches exclus ; sessions sans
    leurs lignes (structure seule, second appel en --no-data)."""
    database = {"NAME": "gestconf", "USER": "gc", "PASSWORD": "secret-x", "HOST": "db"}
    destination = tmp_path / "dump.sql.gz"
    skipped = backups.dump_mariadb(database, destination, tmp_path)
    first, second = fake_mariadb.calls
    assert first[1].startswith("--defaults-extra-file=")  # toujours la première option
    assert not any("secret-x" in argument for call in fake_mariadb.calls for argument in call)
    assert 'password="secret-x"' in fake_mariadb.option_text
    assert "--single-transaction" in first and "--no-tablespaces" in first
    assert "--ignore-table=gestconf.django_session" in first
    assert "--ignore-table=gestconf.gestconf_cache" in first
    assert second[-2:] == ["gestconf", "django_session"] and "--no-data" in second
    assert "django_session" in skipped
    assert not list(tmp_path.glob(".client-*"))  # fichier d'options effacé
    assert gzip.decompress(destination.read_bytes()).count(b"-- Dump completed") == 2


def test_s2_mysql_client_dump_disables_column_statistics(fake_mariadb, monkeypatch, tmp_path):
    monkeypatch.setattr(backups, "is_mariadb_tool", lambda tool: False)
    backups.dump_mariadb({"NAME": "g"}, tmp_path / "d.sql.gz", tmp_path)
    assert "--column-statistics=0" in fake_mariadb.calls[0]


@pytest.mark.parametrize(
    ("output", "code", "message"),
    [
        (b"CREATE TABLE t;\n", 0, "Dump incomplet"),
        (b"", 2, "erreur simulee"),
    ],
)
def test_s2_failed_or_truncated_dump_leaves_no_backup(
    fake_mariadb, backup_settings, settings, monkeypatch, output, code, message
):
    fake_mariadb.output, fake_mariadb.code = output, code
    monkeypatch.setattr(type(connections["default"]), "vendor", "mysql")
    monkeypatch.setitem(connection.settings_dict, "NAME", "gestconf")
    with pytest.raises(backups.BackupError, match=message):
        backups.backup()
    assert list(Path(settings.GESTCONF_BACKUP_DIR).iterdir()) == []


@SQLITE_ONLY
def test_s2_backup_db_writes_dump_manifest_heartbeat_and_audit(backup_settings, settings):
    output = io.StringIO()
    call_command("backup_db", stdout=output)
    directory = Path(settings.GESTCONF_BACKUP_DIR)
    assert directory.stat().st_mode & 0o777 == 0o700
    (dump,) = directory.glob("gestconf-*.sql.gz")
    assert b"CREATE TABLE" in gzip.decompress(dump.read_bytes())
    manifest = json.loads(backups.manifest_path(dump).read_text())
    assert manifest["database"]["sha256"] == backups.sha256_of(dump)
    assert manifest["database"]["file"] == dump.name
    assert manifest["migrations"]["core"].startswith("00")
    roots = manifest["files"]["roots"]
    assert ["private/submissions/a.pdf", 10] in roots["files"]
    assert ["public/logo.png", 3] in roots["files"]
    assert manifest["files"]["count"] == 2
    assert dump.stat().st_mode & 0o777 == 0o600
    heartbeat = CronHeartbeat.objects.get(name="backup_db")
    assert heartbeat.last_status == HeartbeatStatus.OK and heartbeat.last_success_at
    assert backups.latest_backup_success() == heartbeat.last_success_at
    assert AuditLog.objects.filter(action="backup.created").exists()


def test_s2_backup_db_required_fails_when_another_backup_runs(backup_settings):
    """Avant migrate (deploy.sh), une sauvegarde déjà en cours arrête le déploiement."""
    with command_lock("backup_db") as acquired:
        assert acquired
        output = io.StringIO()
        call_command("backup_db", stdout=output)  # cron : sortie sans erreur
        assert "une autre exécution est en cours" in output.getvalue()
        with pytest.raises(CommandError, match="déjà en cours"):
            call_command("backup_db", "--required")


def test_s3_manifest_detects_an_altered_dump(tmp_path):
    dump = tmp_path / "gestconf-20261012T020000Z.sql.gz"
    dump.write_bytes(b"original")
    manifest = {"format": 1, "database": {"sha256": backups.sha256_of(dump)}}
    backups.manifest_path(dump).write_text(json.dumps(manifest))
    assert backups.read_manifest(dump)["format"] == 1
    dump.write_bytes(b"altere")
    with pytest.raises(backups.BackupError, match="altérée"):
        backups.read_manifest(dump)
    backups.manifest_path(dump).unlink()
    with pytest.raises(backups.BackupError, match="Manifeste absent"):
        backups.read_manifest(dump)


def test_s3_files_are_copied_into_empty_folders_then_checked(tmp_path):
    source = tmp_path / "snapshot"
    (source / "files" / "private").mkdir(parents=True)
    (source / "files" / "private" / "a.pdf").write_bytes(b"12345")
    roots = {"files": tmp_path / "restored"}
    backups.copy_files(source, roots)
    manifest = {
        "files": {"roots": {"files": [["private/a.pdf", 5], ["private/b.pdf", 3]]}},
    }
    report = backups.RestoreReport(dump=Path("d"), created_at="x")
    backups.verify_files(manifest, roots, report)
    assert report.missing_files == ["files/private/b.pdf"] and not report.complete
    (roots["files"] / "private" / "a.pdf").write_bytes(b"1")
    report = backups.RestoreReport(dump=Path("d"), created_at="x")
    backups.verify_files(manifest, roots, report)
    assert report.size_mismatches == ["files/private/a.pdf"]
    with pytest.raises(backups.BackupError, match="n'est pas vide"):
        backups.copy_files(source, roots)


@SQLITE_ONLY
def test_s3_restore_is_refused_outside_mariadb(backup_settings, settings):
    call_command("backup_db", stdout=io.StringIO())
    (dump,) = Path(settings.GESTCONF_BACKUP_DIR).glob("gestconf-*.gz")
    with pytest.raises(CommandError, match="MariaDB"):
        call_command("restore_db", str(dump))


@pytest.mark.mariadb_only
@pytest.mark.django_db(transaction=True)
def test_s2_s3_mariadb_backup_then_restore_into_an_empty_database(backup_settings, settings):
    """Dump réel par mariadb-dump, puis chargement dans une base neuve (contrôle de la
    restauration avant toute donnée réelle, D18) ; une base non vide est refusée."""
    from apps.core.models import CronHeartbeat as Heartbeat

    Heartbeat.objects.create(name="witness", processed_count=7)
    result = backups.backup()
    text = gzip.decompress(result.dump.read_bytes())
    assert text.count(backups.DUMP_COMPLETED) == 2
    assert b"INSERT INTO `django_session`" not in text
    target = dict(connection.settings_dict, NAME=connection.settings_dict["NAME"] + "_restore")
    with connection.cursor() as cursor:
        cursor.execute(f"DROP DATABASE IF EXISTS `{target['NAME']}`")
        cursor.execute(f"CREATE DATABASE `{target['NAME']}` CHARACTER SET utf8mb4")
    try:
        backups.load_mariadb(result.dump, target, Path(settings.GESTCONF_BACKUP_DIR))
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT processed_count FROM `{target['NAME']}`.core_cronheartbeat "  # noqa: S608
                "WHERE name = 'witness'"
            )
            assert cursor.fetchone() == (7,)
            cursor.execute(f"SELECT COUNT(*) FROM `{target['NAME']}`.django_session")  # noqa: S608
            assert cursor.fetchone() == (0,)
        with pytest.raises(backups.BackupError, match="n'est pas vide"):
            backups.load_mariadb(result.dump, target, Path(settings.GESTCONF_BACKUP_DIR))
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{target['NAME']}`")


def test_s3_backup_db_is_a_no_op_on_an_empty_database(backup_settings, monkeypatch, settings):
    """Premier déploiement : deploy.sh lance backup_db avant le tout premier migrate."""
    monkeypatch.setattr(type(connections["default"].introspection), "table_names", lambda *a: [])
    output = io.StringIO()
    call_command("backup_db", "--required", stdout=output)
    assert "base vide" in output.getvalue()
    assert not Path(settings.GESTCONF_BACKUP_DIR).exists()
