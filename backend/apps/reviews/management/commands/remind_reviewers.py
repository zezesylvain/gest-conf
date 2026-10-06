"""Relances des relecteurs avant et après l'échéance (plan L4, H15), lancées par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand
from apps.reviews.services.reminders import remind_reviewers


class Command(LockedCommand):
    help = (
        "Relance les relecteurs sept jours et un jour avant l'échéance, puis après elle, une "
        "fois chacune. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        sent = remind_reviewers()
        if options["verbosity"] >= 1:
            self.stdout.write(f"remind_reviewers : {sent} relance(s)")
        return sent
