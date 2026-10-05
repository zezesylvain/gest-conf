"""Rechiffre les secrets 2FA avec la première clé de ``GESTCONF_MFA_ENCRYPTION_KEYS``
(plan L1 §4.10 ; procédure dans deploy/README.md).

1. Placer la nouvelle clé EN TÊTE de la liste, l'ancienne restant derrière ; redémarrer.
2. ``manage.py rotate_mfa_keys`` (idempotente).
3. Retirer l'ancienne clé ; redémarrer.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.accounts.services.mfa import rotate_mfa_keys
from apps.core.audit import record
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Rechiffre tous les secrets 2FA avec la première clé configurée."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true", help="Vérifie le déchiffrement sans rien écrire."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        count = rotate_mfa_keys(dry_run=options["dry_run"])
        if options["dry_run"]:
            self.stdout.write(f"{count} authentificateur(s) déchiffrable(s) ; rien n'est écrit.")
            return
        record("mfa.keys_rotated", actor=command_actor(), after={"count": count})
        self.stdout.write(f"{count} authentificateur(s) rechiffré(s).")
