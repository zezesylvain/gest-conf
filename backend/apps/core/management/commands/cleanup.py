"""Purges quotidiennes (cron, plan L1 §8.4, décision D15). Exemple de crontab :

    17 3 * * *  <app>/deploy/cron.sh cleanup

- Purges de **sécurité** toujours appliquées : sessions expirées (``clearsessions``),
  entrées expirées des deux tables de cache, corps des e-mails sensibles.
- Purges du **cadre légal** (durées de D15) **simulées** tant que
  ``GESTCONF_RETENTION_ENFORCE`` n'est pas activé : le rapport indique ce qui serait purgé.

Résumé dans le battement de cœur ; en mode actif, une entrée d'audit ``retention.applied``.
Idempotente : un second passage immédiat ne trouve plus rien à purger.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import CommandParser
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.actor import Actor
from apps.core.audit import AuditAction, record
from apps.core.management.base import CommandResult, LockedCommand
from apps.core.retention import RetentionMode, run_rules


class Command(LockedCommand):
    help = gettext_lazy(
        "Purges quotidiennes : sécurité toujours ; durées de conservation (D15) en simulation "
        "tant que GESTCONF_RETENTION_ENFORCE n'est pas activé."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=_("Simule aussi les purges du cadre légal, même si elles sont activées."),
        )

    def run(self, **options: Any) -> CommandResult:
        enforce = settings.GESTCONF_RETENTION_ENFORCE and not options["dry_run"]
        now = timezone.now()
        actor = Actor.system("job:cleanup")
        report = run_rules(now, actor=actor, enforce_legal=enforce)
        for name, entry in report.items():
            label = (
                _("purgés")
                if entry["mode"] == RetentionMode.APPLIED
                else _("seraient purgés (simulation)")
            )
            suffix = f" [{entry['error']}]" if "error" in entry else ""
            self.stdout.write(f"{name} : {entry['count']} {label}{suffix}")
        if enforce:
            with transaction.atomic():
                record(
                    AuditAction.RETENTION_APPLIED,
                    actor=actor,
                    after={name: entry["count"] for name, entry in report.items()},
                )
        errors = sorted(name for name, entry in report.items() if "error" in entry)
        processed = sum(
            entry["count"] for entry in report.values() if entry["mode"] == RetentionMode.APPLIED
        )
        return CommandResult(
            processed=processed,
            summary={"enforce": enforce, "rules": report},
            succeeded=not errors,
            error=_("Purges en erreur : %(rules)s") % {"rules": ", ".join(errors)}
            if errors
            else "",
        )
