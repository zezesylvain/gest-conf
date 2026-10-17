"""Édition de démonstration (plan L9, S10) : ``manage.py seed_demo --confirm-fictitious``.

Refusée sans confirmation, dès que la base contient des données réelles, ou si l'édition
``DEMO`` existe déjà. Avant : ``backup_db`` ; après la recette : restauration de cette
sauvegarde dans une base neuve (``docs/L9-runbook-o2switch.md``).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.audit import record
from apps.core.management.base import command_actor
from apps.qa.demo import DEMO_EDITION, demo_exists, seed_demo
from apps.qa.fictitious import CONFIRM_OPTION, ensure_fictitious_only


class Command(BaseCommand):
    help = "Crée l'édition de démonstration (un compte fictif par rôle) pour la recette."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(CONFIRM_OPTION, action="store_true", dest="confirmed")

    def handle(self, *args: Any, **options: Any) -> None:
        ensure_fictitious_only(confirmed=options["confirmed"])
        if demo_exists():
            raise CommandError(f"L'édition {DEMO_EDITION} existe déjà : restaurer la sauvegarde.")
        report = seed_demo()
        record(
            "qa.demo_seeded",
            actor=command_actor(),
            after={"edition": report.edition, "accounts": len(report.accounts)},
        )
        self.stdout.write(f"seed_demo : édition {DEMO_EDITION} créée, courante sur le portail.")
        for email, role in report.accounts:
            self.stdout.write(f"  {email} : {role}")
        # Affichés une seule fois : comptes fictifs d'une base restaurée après la recette.
        self.stdout.write(f"  mot de passe des comptes : {report.password}")
        self.stdout.write(f"  secret TOTP (rôles de gestion) : {report.totp_secret}")
