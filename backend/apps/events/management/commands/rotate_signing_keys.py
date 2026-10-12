"""Rechiffre les certificats PAdES déposés avec la première clé de
``GESTCONF_SIGNING_ENCRYPTION_KEYS`` (revue de sécurité L9.5 ; procédure dans
deploy/README.md, comme ``rotate_mfa_keys``).

1. Placer la nouvelle clé EN TÊTE de la liste, l'ancienne restant derrière ; redémarrer.
2. ``manage.py rotate_signing_keys`` (``--dry-run`` : vérifie le déchiffrement).
3. Retirer l'ancienne clé ; redémarrer.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.core.audit import record
from apps.core.management.base import command_actor
from apps.events.services.certificates import rotate_signing_keys


class Command(BaseCommand):
    help = "Rechiffre les certificats de signature avec la première clé configurée."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run", action="store_true", help="Vérifie le déchiffrement sans rien écrire."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        count = rotate_signing_keys(dry_run=options["dry_run"])
        if options["dry_run"]:
            self.stdout.write(f"{count} certificat(s) déchiffrable(s) ; rien n'est écrit.")
            return
        record("certificates.signing_keys_rotated", actor=command_actor(), after={"count": count})
        self.stdout.write(f"{count} certificat(s) rechiffré(s).")
