"""Change le statut d'une édition par commande (retour en arrière compris, motif obligatoire)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.conferences.models import Edition, EditionStatus
from apps.conferences.services import set_edition_status
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Change le statut d'une édition (draft, published, archived)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("code")
        parser.add_argument("status", choices=EditionStatus.values)
        parser.add_argument("--reason", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["reason"].strip():
            raise CommandError("Motif obligatoire (--reason).")
        edition = Edition.objects.filter(code=options["code"]).first()
        if edition is None:
            raise CommandError("Édition inconnue.")
        try:
            edition = set_edition_status(
                edition, options["status"], actor=command_actor(), reason=options["reason"]
            )
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Édition {edition.code} : {edition.status}.")
