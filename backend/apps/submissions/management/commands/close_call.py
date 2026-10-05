"""Clôture de l'appel à communications (plan L3 §2.2), lancée par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.actor import Actor
from apps.core.management.base import LockedCommand
from apps.submissions.services import close_calls


class Command(LockedCommand):
    help = (
        "Fait passer en recevabilité les soumissions des éditions dont l'appel est clos, "
        "sauf dérogation en cours (traitées au premier passage après son échéance). "
        "Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        moved = close_calls(actor=Actor.system("cron:close_call"))
        if options["verbosity"] >= 1:
            self.stdout.write(f"close_call : {moved} soumission(s) en recevabilité")
        return moved
