"""Restauration d'une sauvegarde dans une base et des dossiers vides (plan L9, S3).

À lancer avec un ``DATABASE_URL`` qui désigne une base **neuve** : la commande refuse une
base qui contient déjà des tables. Vérifie l'empreinte du dump (manifeste), recopie les
fichiers rapatriés (``--files-from``, instantané de ``deploy/pull-backups.sh``), compare
fichiers et manifeste, recrée les tables du cache et signale les migrations en attente.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.audit import record
from apps.core.backups import BackupError, restore
from apps.core.management.base import command_actor

LISTED_MAX = 20


class Command(BaseCommand):
    help = "Restaure un dump (et ses fichiers) dans une base et des dossiers vides."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "dump", type=Path, help="Dump gestconf-<date>.sql.gz (manifeste à côté)."
        )
        parser.add_argument(
            "--files-from",
            type=Path,
            help="Instantané des fichiers rapatriés (sous-dossiers « files », « private »).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            report = restore(options["dump"], files_from=options["files_from"])
        except BackupError as error:
            raise CommandError(str(error)) from error
        record(
            "backup.restored",
            actor=command_actor(),
            after={
                "file": report.dump.name,
                "created_at": report.created_at,
                "missing_files": len(report.missing_files),
                "size_mismatches": len(report.size_mismatches),
            },
        )
        self.stdout.write(
            f"restore_db : base restaurée depuis {report.dump.name} ({report.created_at})."
        )
        for label, items in (
            ("fichier absent", report.missing_files),
            ("taille différente", report.size_mismatches),
        ):
            for item in items[:LISTED_MAX]:
                self.stdout.write(f"restore_db : {label} : {item}")
            if len(items) > LISTED_MAX:
                self.stdout.write(f"restore_db : … et {len(items) - LISTED_MAX} autres ({label}).")
        if report.pending_migrations:
            self.stdout.write(
                "restore_db : migrations en attente (non appliquées) : "
                + ", ".join(report.pending_migrations)
            )
        if not report.complete:
            raise CommandError("Restauration incomplète : fichiers manquants ou différents.")
        self.stdout.write("restore_db : fichiers conformes au manifeste. Lancer check_integrity.")
