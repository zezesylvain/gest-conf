"""Rappels des brouillons avant la clôture de l'appel (plan L3, F13), lancés par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand
from apps.submissions.services import remind_drafts


class Command(LockedCommand):
    help = (
        "Rappelle aux auteurs leurs brouillons sept jours puis la veille de la clôture "
        "(e-mail et cloche). Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        sent = remind_drafts()
        if options["verbosity"] >= 1:
            self.stdout.write(f"remind_drafts : {sent} rappel(s)")
        return sent
