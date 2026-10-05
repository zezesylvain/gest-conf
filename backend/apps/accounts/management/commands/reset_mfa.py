"""Réinitialise la 2FA d'un compte (perte de l'appareil ; plan L1 §4.3, §9.4).

À n'exécuter qu'après vérification de l'identité hors bande. Motif obligatoire, audit
``mfa.reset`` et e-mail à l'adresse principale. Un rôle de gestion devra se réenrôler.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services.mfa import reset_mfa
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Supprime la double authentification d'un compte (TOTP et codes de secours)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--reason", required=True, help="Motif (journalisé).")

    def handle(self, *args: Any, **options: Any) -> None:
        if not options["reason"].strip():
            raise CommandError("Motif obligatoire (--reason).")
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("Aucun compte avec cette adresse.")
        count = reset_mfa(user, actor=command_actor(), reason=options["reason"])
        if count == 0:
            self.stdout.write(f"Compte #{user.pk} : aucune double authentification active.")
        else:
            self.stdout.write(f"Compte #{user.pk} : double authentification réinitialisée.")
