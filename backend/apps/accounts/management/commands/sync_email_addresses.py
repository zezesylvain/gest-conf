"""Crée l'``EmailAddress`` d'allauth des comptes qui n'en ont pas (plan L1 §3.8).

Les comptes créés avant allauth (lot L0, par commande) n'ont pas de ligne
``EmailAddress`` : sans elle, la connexion répond 401 avec le flux
``verify_email``. ``--verified`` les marque vérifiées (comptes créés par
l'opérateur, adresse connue) ; sinon, la personne recevra un lien à sa connexion.
"""

from __future__ import annotations

from typing import Any

from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.accounts.models import User
from apps.core.audit import record
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Crée l'adresse allauth (principale) des comptes qui n'en ont pas."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--verified", action="store_true", help="Marquer les adresses créées comme vérifiées."
        )
        parser.add_argument("--dry-run", action="store_true", help="Compter sans rien créer.")

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        missing = User.objects.exclude(
            pk__in=EmailAddress.objects.values_list("user_id", flat=True)
        ).filter(anonymized_at__isnull=True)
        count = 0
        for user in missing.iterator():
            if not options["dry_run"]:
                EmailAddress.objects.create(
                    user=user, email=user.email, primary=True, verified=options["verified"]
                )
            count += 1
        if not options["dry_run"]:
            record(
                "command.sync_email_addresses",
                actor=command_actor(),
                after={"created": count, "verified": options["verified"]},
            )
        mode = "à créer (simulation)" if options["dry_run"] else "créée(s)"
        self.stdout.write(f"{count} adresse(s) {mode}.")
