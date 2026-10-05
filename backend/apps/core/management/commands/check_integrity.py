"""Contrôles d'intégrité quotidiens (plan L1 §8.4, étude §11.5) : lecture seule.

Les anomalies sont journalisées et envoyées aux opérateurs (``GESTCONF_OPERATORS``).
"""

from __future__ import annotations

from typing import Any

from apps.core.actor import Actor
from apps.core.alerts import notify_operators
from apps.core.audit import record
from apps.core.integrity import integrity_checks
from apps.core.management.base import LockedCommand


class Command(LockedCommand):
    help = "Contrôles d'intégrité (doublons, cohérence rôles/invitations, cache, tâches)."

    def run(self, *args: Any, **options: Any) -> int:
        problems: dict[str, list[str]] = {}
        for name, check in integrity_checks():
            found = check()
            if found:
                problems[name] = found
            if options["verbosity"] >= 1:
                self.stdout.write(f"check_integrity : {name} -> {len(found)} anomalie(s)")
        record(
            "integrity.checked",
            actor=Actor.system("cron:check_integrity"),
            after={"problems": {name: len(items) for name, items in problems.items()}},
        )
        if problems:
            notify_operators(
                "[GEST-CONF] Contrôle d'intégrité : anomalies",
                {name: " | ".join(items) for name, items in problems.items()},
            )
        return sum(len(items) for items in problems.values())
