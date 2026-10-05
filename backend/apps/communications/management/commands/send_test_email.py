"""Met en file un e-mail de test (jalon J-tech, plan L1 §13) : le cron l'enverra.

Vérifie de bout en bout la chaîne réelle : file, cron (``run_jobs``), fournisseur,
délivrabilité (SPF, DKIM). Pas d'envoi immédiat : c'est le passage du cron qui
est contrôlé.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.validators import validate_email
from django.db import transaction

from apps.communications.services import queue_email
from apps.core.audit import mask_email, record
from apps.core.management.base import command_actor

TEST_TEMPLATE = "communications/email/test"


class Command(BaseCommand):
    help = "Met en file un e-mail de test vers l'adresse indiquée (envoyé au passage du cron)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("address", help="Adresse destinataire.")
        parser.add_argument(
            "--locale",
            choices=[code for code, _name in settings.LANGUAGES],
            default=settings.LANGUAGE_CODE,
        )

    def handle(self, *args: Any, **options: Any) -> None:
        address = options["address"]
        try:
            validate_email(address)
        except ValidationError as exc:
            raise CommandError(f"Adresse invalide : {address}") from exc
        with transaction.atomic():
            email = queue_email(
                template_code=TEST_TEMPLATE, to_email=address, locale=options["locale"]
            )
            record(
                "email.test_queued",
                actor=command_actor(),
                obj=email,
                after={"to": mask_email(address), "locale": email.locale},
            )
        self.stdout.write(
            f"E-mail de test #{email.pk} mis en file ; il partira au prochain passage de "
            "« run_jobs » (cron). Suivi : manage.py outbox."
        )
