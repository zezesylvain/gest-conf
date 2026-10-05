"""Consultation du journal d'audit par l'opérateur (plan L1 §7.4).

Seul accès aux entrées sans édition (connexions, comptes) et au contexte réseau
(IP, navigateur), que l'API ne renvoie jamais. La consultation est elle-même
journalisée (``audit.queried``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User
from apps.core.audit import mask_email, record
from apps.core.management.base import command_actor
from apps.core.models import AuditLog


class Command(BaseCommand):
    help = "Affiche les entrées du journal d'audit (filtres : action, compte, période)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--action", help="Code exact (auth.login) ou préfixe (auth.).")
        parser.add_argument("--email", help="Compte acteur OU objet de l'entrée.")
        parser.add_argument("--since", help="Date de début, AAAA-MM-JJ (UTC).")
        parser.add_argument("--limit", type=int, default=50)

    def handle(self, *args: Any, **options: Any) -> None:
        entries = AuditLog.objects.select_related("actor").order_by("-at", "-id")
        filters: dict[str, Any] = {}
        if options["action"]:
            action = options["action"]
            entries = (
                entries.filter(action__startswith=action)
                if action.endswith(".")
                else entries.filter(action=action)
            )
            filters["action"] = action
        if options["email"]:
            user = User.objects.filter(email__iexact=options["email"].strip()).first()
            if user is None:
                raise CommandError("Aucun compte avec cette adresse.")
            entries = entries.filter(actor=user) | entries.filter(
                object_type="accounts.user", object_id=str(user.pk)
            )
            filters["email"] = mask_email(user.email)
        if options["since"]:
            try:
                day = datetime.strptime(options["since"], "%Y-%m-%d").date()
            except ValueError as exc:
                raise CommandError("--since : format AAAA-MM-JJ attendu.") from exc
            entries = entries.filter(at__gte=datetime.combine(day, time.min, tzinfo=UTC))
            filters["since"] = day.isoformat()

        for entry in entries[: options["limit"]]:
            actor = (
                f"user#{entry.actor_id}"
                if entry.actor_id
                else entry.actor_label or entry.actor_kind
            )
            self.stdout.write(
                f"{entry.at:%Y-%m-%d %H:%M:%S}\t{entry.action}\t{actor}\t"
                f"{entry.object_type}#{entry.object_id}\tip={entry.ip or '-'}\t"
                f"req={entry.request_id or '-'}\t{entry.reason}\t"
                f"avant={json.dumps(entry.before, ensure_ascii=False)}\t"
                f"après={json.dumps(entry.after, ensure_ascii=False)}"
            )
        record("audit.queried", actor=command_actor(), after={"filters": filters})
