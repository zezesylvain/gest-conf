"""Désigne l'édition courante d'une conférence (servie par /v1/public/editions/current)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.conferences.models import Edition
from apps.conferences.services import set_current_edition
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Désigne l'édition courante (par son code)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("code")

    def handle(self, *args: Any, **options: Any) -> None:
        edition = Edition.objects.select_related("conference").filter(code=options["code"]).first()
        if edition is None:
            raise CommandError("Édition inconnue.")
        set_current_edition(edition.conference, edition, actor=command_actor())
        self.stdout.write(f"Édition courante : {edition.code}.")
