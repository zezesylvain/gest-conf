"""Rappels de la confirmation de présentation (plan L5, §9), lancés par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand
from apps.program.services.reminders import remind_presentations


class Command(LockedCommand):
    help = (
        "Rappelle aux auteurs de confirmer leur présentation trois jours, puis dix jours après "
        "la réception de la version finale, une fois chacun. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        sent = remind_presentations()
        if options["verbosity"] >= 1:
            self.stdout.write(f"remind_presentations : {sent} rappel(s)")
        return sent
