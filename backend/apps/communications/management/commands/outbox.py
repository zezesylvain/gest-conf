"""Suivi du registre d'envoi (plan L1 §8.3) : liste par statut, renvoi d'un e-mail en échec."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import EmailNotRetryable, retry_email
from apps.core.audit import mask_email
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Liste les e-mails du registre (sans leur corps) ou renvoie un e-mail en échec."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--status", choices=OutboxStatus.values, help="Filtrer par statut.")
        parser.add_argument("--limit", type=int, default=50)
        parser.add_argument("--retry", type=int, metavar="ID", help="Remettre en file cet e-mail.")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["retry"] is not None:
            try:
                email = retry_email(options["retry"], actor=command_actor())
            except OutboxEmail.DoesNotExist as exc:
                raise CommandError(f"E-mail #{options['retry']} introuvable.") from exc
            except EmailNotRetryable as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(f"E-mail #{email.pk} remis en file.")
            return

        emails = OutboxEmail.objects.order_by("-created_at", "-id")
        if options["status"]:
            emails = emails.filter(status=options["status"])
        for email in emails[: options["limit"]]:
            # Destinataire masqué : la sortie de la commande peut finir dans un journal.
            self.stdout.write(
                f"#{email.pk}\t{email.status}\t{email.created_at:%Y-%m-%d %H:%M}\t"
                f"{email.template_code}\t{mask_email(email.to_email)}\t"
                f"essais={email.attempts}\t{email.last_error}"
            )
