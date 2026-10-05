"""Enregistre une mise en ligne du portail (E9) : appelée par ``deploy.sh --portal-only``
après la synchronisation du portail pré-rendu ; le compteur de modifications non publiées
de la gestion repart de zéro. Auditée (``portal.published``)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.dateparse import parse_datetime

from apps.conferences.models import Edition
from apps.core.errors import Invalid
from apps.core.management.base import command_actor
from apps.portal.services import mark_published


class Command(BaseCommand):
    help = "Enregistre la mise en ligne du portail d'une édition (par son code)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("code")
        parser.add_argument("--release", default="", help="Version déployée (empreinte de commit).")
        parser.add_argument(
            "--built-at",
            default=None,
            help="Début du pré-rendu (ISO 8601 avec fuseau) ; défaut : maintenant.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        edition = Edition.objects.filter(code=options["code"]).first()
        if edition is None:
            raise CommandError("Édition inconnue.")
        built_at = None
        if options["built_at"]:
            built_at = parse_datetime(options["built_at"])
            if built_at is None:
                raise CommandError("--built-at : date ISO 8601 attendue.")
        try:
            publication = mark_published(
                edition, release=options["release"], built_at=built_at, actor=command_actor()
            )
        except Invalid as error:
            raise CommandError(str(error.message)) from error
        at = f"{publication.published_at:%Y-%m-%d %H:%M}"
        self.stdout.write(f"Portail de {edition.code} mis en ligne le {at} UTC.")
