"""Exporte les données d'un compte (demande reçue par courrier ou e-mail, plan L1 §4.9).

Écrit le JSON dans un fichier (droits 600) ou sur la sortie standard. Audit
``account.exported`` (acteur : commande).
"""

from __future__ import annotations

import json
import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.accounts.services.personal_data import export_user_data
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Exporte en JSON les données personnelles d'un compte."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--output", help="Fichier de sortie (sinon : sortie standard).")

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        if user is None:
            raise CommandError("Aucun compte avec cette adresse.")
        data = json.dumps(
            export_user_data(user, actor=command_actor()), ensure_ascii=False, indent=2
        )
        output = options.get("output")
        if not output:
            self.stdout.write(data)
            return
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(data)
        self.stdout.write(f"Export écrit dans {output} (droits 600).")
