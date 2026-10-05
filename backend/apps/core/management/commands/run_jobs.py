"""Exécute les tâches en file (cron toutes les 1 à 5 minutes, plan L1 §8.2 et §8.4)."""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import CommandParser

from apps.core import jobs
from apps.core.cache_maintenance import purge_expired_cache_entries
from apps.core.management.base import LockedCommand


class Command(LockedCommand):
    help = "Exécute les tâches en file (verrouillé, idempotent, budget de temps)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--max-seconds",
            type=float,
            default=240,
            help="Budget de temps, inférieur à l'intervalle du cron (défaut : 240).",
        )
        parser.add_argument(
            "--batch-size", type=int, default=jobs.BATCH_SIZE, help="Taille des lots."
        )

    def run(self, *args: Any, **options: Any) -> int:
        deadline = time.monotonic() + options["max_seconds"]
        recovered = jobs.recover_stale()
        purged = purge_expired_cache_entries()
        processed = jobs.run_pending(deadline=deadline, batch_size=options["batch_size"])
        if options["verbosity"] >= 1:
            self.stdout.write(
                f"run_jobs : {processed} tâche(s) exécutée(s), {recovered} reprise(s), "
                f"cache purgé : {purged}."
            )
        return processed
