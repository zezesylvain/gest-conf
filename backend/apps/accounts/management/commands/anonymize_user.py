"""Anonymise un compte (demande reçue par courrier ou e-mail, plan L1 §4.9, RG-18).

Motif obligatoire. Refusée tant que la personne détient des rôles de gestion actifs :
les retirer d'abord (``revoke_role``). Irréversible.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services.personal_data import anonymize_user
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Anonymise définitivement un compte (adresse, profil, 2FA, sessions...)."

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
            anonymize_user(user, actor=command_actor(), reason=options["reason"])
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Compte #{user.pk} anonymisé.")
