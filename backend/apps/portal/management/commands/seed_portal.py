"""Recrée les pages du site, les sections « données » et le menu manquants d'une édition
(idempotent ; aucune composition). Le seed s'exécute déjà à la création d'une édition."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.conferences.models import Edition
from apps.core.audit import record
from apps.core.management.base import command_actor
from apps.portal.services import seed_portal


class Command(BaseCommand):
    help = "Complète le contenu de départ du portail d'une édition (par son code)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("code")

    def handle(self, *args: Any, **options: Any) -> None:
        edition = Edition.objects.filter(code=options["code"]).first()
        if edition is None:
            raise CommandError("Édition inconnue.")
        with transaction.atomic():
            created = seed_portal(edition)
            if any(created.values()):
                record("portal.seeded", actor=command_actor(), edition=edition, after=created)
        self.stdout.write(
            f"{edition.code} : {created['pages']} page(s), {created['sections']} section(s), "
            f"{created['menu_items']} entrée(s) de menu créées."
        )
