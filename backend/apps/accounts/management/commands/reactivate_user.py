"""Réactive un compte désactivé (plan L1 §9.4), avec motif. Jamais un compte anonymisé."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services import reactivate_user
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Réactive un compte désactivé par deactivate_user."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--reason", required=True, help="Motif (journalisé).")

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["reason"].strip():
            raise CommandError("Motif obligatoire (--reason).")
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("Aucun compte avec cette adresse.")
        try:
            reactivate_user(user, reason=options["reason"], actor=command_actor())
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Compte #{user.pk} réactivé.")
