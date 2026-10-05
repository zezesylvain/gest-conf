"""Crée la conférence (D1 : autorité de plateforme exercée par commande, auditée)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.conferences.services import create_conference
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Crée une conférence (slug, nom FR, nom EN)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--slug", required=True)
        parser.add_argument("--name-fr", required=True)
        parser.add_argument("--name-en", default="")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            conference = create_conference(
                slug=options["slug"],
                name_fr=options["name_fr"],
                name_en=options["name_en"],
                actor=command_actor(),
            )
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Conférence « {conference.slug} » créée (#{conference.pk}).")
