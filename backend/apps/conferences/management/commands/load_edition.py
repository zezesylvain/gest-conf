"""Charge une édition réelle depuis un dossier versionné (décision T3, ``apps.conferences.loader``).

    python manage.py load_edition data/editions/icha-2027 --admin-email … [--draft]

Tout ou rien (une transaction) ; refusé si l'édition existe déjà. ``--draft`` laisse
l'édition en brouillon, non courante, pour relecture dans la gestion avant publication.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.conferences.loader import EditionDataError, load_edition
from apps.core.errors import DomainError


class Command(BaseCommand):
    help = "Charge une édition (conférence, portail, partenaires…) depuis un dossier de données."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("directory", type=Path)
        parser.add_argument("--admin-email", default="")
        parser.add_argument("--locale", default="fr", choices=("fr", "en"))
        parser.add_argument("--draft", action="store_true", help="Ne pas publier l'édition.")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            report = load_edition(
                options["directory"],
                admin_email=options["admin_email"],
                locale=options["locale"],
                publish=not options["draft"],
            )
        except EditionDataError as exc:
            raise CommandError(str(exc)) from exc
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        created = "créée" if report.conference_created else "existante"
        state = "brouillon" if options["draft"] else "publiée et courante"
        self.stdout.write(
            f"Édition {report.edition} chargée ({state}), conférence « {report.conference} » "
            f"{created}."
        )
        for name, count in report.counts.items():
            self.stdout.write(f"  {name} : {count}")
        if report.admin:
            self.stdout.write(f"  {report.admin}")
