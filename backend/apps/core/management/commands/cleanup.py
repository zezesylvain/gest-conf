"""Purges quotidiennes (plan L1 §8.4, D15). Squelette en L1.2, complété en L1.8."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.management.base import LockedCommand
from apps.core.retention import retention_tasks


class Command(LockedCommand):
    help = (
        "Purges quotidiennes : sessions expirées, données à durée de conservation limitée. "
        "Les durées non validées (D15) restent en simulation tant que "
        "GESTCONF_RETENTION_ENFORCED est faux."
    )

    def run(self, *args: Any, **options: Any) -> int:
        call_command("clearsessions")
        now = timezone.now()
        enforced = settings.GESTCONF_RETENTION_ENFORCED
        summary: dict[str, dict[str, Any]] = {}
        total = 0
        for task in retention_tasks():
            dry_run = not (task.security or enforced)
            with transaction.atomic():
                count = task.function(dry_run, now)
            summary[task.name] = {"count": count, "dry_run": dry_run}
            if not dry_run:
                total += count
            if options["verbosity"] >= 1:
                mode = "simulation" if dry_run else "appliqué"
                self.stdout.write(f"cleanup : {task.name} -> {count} ({mode})")
        record("retention.applied", actor=Actor.system("cron:cleanup"), after={"tasks": summary})
        return total
