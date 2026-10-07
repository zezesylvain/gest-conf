"""Suivi du registre d'envoi (plan L1 §8.3) :

    python manage.py outbox [--status failed] [--limit 50]
    python manage.py outbox --retry <id> --reason "…"

La liste n'affiche que l'adresse masquée (minimisation). ``--retry`` remet en file un
e-mail en échec (statut ``failed``) : action sensible (correspondance d'un tiers),
auditée (``command.outbox_retry``), motif obligatoire.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import CommandError, CommandParser
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import retry_failed_email
from apps.core.audit import AuditAction, record, snapshot
from apps.core.management.base import (
    LockedCommand,
    add_reason_argument,
    command_actor,
    require_reason,
)

DEFAULT_LIMIT = 50


class Command(LockedCommand):
    help = gettext_lazy("Liste les e-mails du registre d'envoi ; renvoie un e-mail en échec.")
    heartbeat_enabled = False

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--status", choices=OutboxStatus.values, help=_("Filtre sur le statut.")
        )
        parser.add_argument(
            "--limit", type=int, default=DEFAULT_LIMIT, help=_("Nombre de lignes affichées.")
        )
        parser.add_argument(
            "--retry", type=int, metavar="ID", help=_("Remet en file l'e-mail en échec ID.")
        )
        add_reason_argument(parser, required_for="--retry")

    def run(self, **options: Any) -> None:
        if options["retry"] is not None:
            self._retry(options["retry"], require_reason(options))
            return
        self._list(options["status"], options["limit"])

    def _list(self, status: str | None, limit: int) -> None:
        if limit <= 0:
            raise CommandError(_("--limit doit être strictement positif."))
        emails = OutboxEmail.objects.order_by("-created_at", "-id")
        if status:
            emails = emails.filter(status=status)
        rows = list(emails[:limit])
        if not rows:
            self.stdout.write(_("Aucun e-mail."))
            return
        for email in rows:
            error = email.last_error.splitlines()[0][:80] if email.last_error else ""
            self.stdout.write(
                f"#{email.pk}  {email.created_at:%Y-%m-%d %H:%M}  {email.status:<9}  "
                f"{email.template_code}  {email.to_email_masked}  "
                f"{_('tentatives')}={email.attempts}  {error}".rstrip()
            )

    def _retry(self, outbox_id: int, reason: str) -> None:
        actor = command_actor()
        with transaction.atomic():
            email = OutboxEmail.objects.select_for_update().filter(pk=outbox_id).first()
            if email is None:
                raise CommandError(_("E-mail introuvable : %(id)s.") % {"id": outbox_id})
            if email.status != OutboxStatus.FAILED:
                raise CommandError(
                    _("Seul un e-mail en échec peut être renvoyé (statut : %(status)s).")
                    % {"status": email.status}
                )
            if email.purged_at is not None:
                raise CommandError(_("Corps purgé : cet e-mail ne peut plus être renvoyé."))
            before = snapshot(email)
            retry_failed_email(email)
            record(
                AuditAction.COMMAND_OUTBOX_RETRY,
                actor=actor,
                obj=email,
                before=before,
                after=snapshot(email),
                reason=reason,
            )
        self.stdout.write(
            _("E-mail n° %(id)s remis en file ; il partira au prochain passage de run_jobs.")
            % {"id": outbox_id}
        )
