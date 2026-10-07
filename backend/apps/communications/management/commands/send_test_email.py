"""Met en file un e-mail de test (opérateur, jalon J-tech, plan L1 §13).

    python manage.py send_test_email --to operateur@exemple.org [--locale en] [--reason "…"]

L'e-mail part au passage suivant de ``run_jobs`` (cron) : c'est précisément ce que le
jalon J-tech vérifie (file, cron, fournisseur, SPF/DKIM). Audité (``command.send_test_email``,
adresse masquée).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError, CommandParser
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.communications.services import TEST_EMAIL, format_timestamp, queue_email
from apps.core.audit import AuditAction, mask_email, record
from apps.core.management.base import LockedCommand, add_reason_argument, command_actor


class Command(LockedCommand):
    help = gettext_lazy("Met en file un e-mail de test, envoyé au prochain passage de run_jobs.")
    heartbeat_enabled = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--to", required=True, help=_("Adresse du destinataire."))
        parser.add_argument(
            "--locale",
            choices=[code for code, _name in settings.LANGUAGES],
            default=settings.LANGUAGE_CODE,
            help=_("Langue de l'e-mail."),
        )
        add_reason_argument(parser)

    def run(self, **options: Any) -> None:
        address = options["to"].strip()
        try:
            validate_email(address)
        except ValidationError as exc:
            raise CommandError(_("Adresse e-mail invalide.")) from exc
        locale = options["locale"]
        actor = command_actor()
        with transaction.atomic():
            email = queue_email(
                TEST_EMAIL.code,
                to_email=address,
                locale=locale,
                context={"timestamp": format_timestamp(timezone.now(), locale)},
            )
            record(
                AuditAction.COMMAND_SEND_TEST_EMAIL,
                actor=actor,
                obj=email,
                after={"to_masked": mask_email(address), "locale": locale},
                reason=options["reason"],
            )
        self.stdout.write(
            _(
                "E-mail de test n° %(id)s mis en file pour %(to)s ; il partira au prochain passage "
                "de run_jobs."
            )
            % {"id": email.pk, "to": mask_email(address)}
        )
