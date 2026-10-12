"""Sauvegarde quotidienne de la base et inventaire des fichiers (plan L9, S2).

Cron quotidien (``deploy/cron.sh backup_db``) et, avant chaque ``migrate``, ``deploy.sh``
(``--required`` : si une sauvegarde tourne déjà, le déploiement s'arrête au lieu de migrer
sans sauvegarde fraîche).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import CommandError, CommandParser
from django.db import connection

from apps.core.audit import record
from apps.core.backups import BackupError, backup
from apps.core.management.base import LockedCommand, command_actor


class Command(LockedCommand):
    help = (
        "Sauvegarde la base (dump compressé et manifeste) dans GESTCONF_BACKUP_DIR, puis "
        "applique la rotation (7 quotidiennes, 4 hebdomadaires, 3 mensuelles)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--required",
            action="store_true",
            help="Échouer (au lieu de sortir sans rien faire) si une sauvegarde est en cours.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # Premier déploiement : base encore vide (ni table, ni battement de cœur possible).
        if not connection.introspection.table_names():
            self.stdout.write("backup_db : base vide, rien à sauvegarder.")
            return
        super().handle(*args, **options)

    def lock_busy(self, name: str, **options: Any) -> None:
        if options["required"]:
            raise CommandError(f"{name} : une sauvegarde est déjà en cours ; réessayer.")
        super().lock_busy(name, **options)

    def run(self, *args: Any, **options: Any) -> int:
        try:
            result = backup()
        except BackupError as error:
            raise CommandError(str(error)) from error
        record(
            "backup.created",
            actor=command_actor(),
            after={"file": result.dump.name, "removed": len(result.removed)},
        )
        if options["verbosity"] >= 1:
            self.stdout.write(f"backup_db : {result.dump} ({result.dump.stat().st_size} octets)")
            for path in result.removed:
                self.stdout.write(f"backup_db : rotation, supprimé {path.name}")
        return 1
