"""Récapitulatif quotidien des tâches du CO (plan L8, N3), lancé par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand
from apps.logistics.services.reminders import remind_tasks


class Command(LockedCommand):
    help = (
        "Envoie à chaque responsable le récapitulatif de ses tâches en retard ou à échéance "
        "sous deux jours, une fois par jour et par édition. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        sent = remind_tasks()
        if options["verbosity"] >= 1:
            self.stdout.write(f"remind_tasks : {sent} récapitulatif(s)")
        return sent
