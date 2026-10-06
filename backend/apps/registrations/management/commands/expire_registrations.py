"""Expiration des commandes impayées à l'échéance (plan L6, J5), lancée par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand
from apps.registrations.services.orders import expire_overdue


class Command(LockedCommand):
    help = (
        "Fait expirer les inscriptions en attente dont l'échéance de paiement est passée "
        "(places d'options et codes promo rendus, e-mail au participant). Un paiement en "
        "ligne en cours est d'abord interrogé. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        expired = expire_overdue()
        if options["verbosity"] >= 1:
            self.stdout.write(f"expire_registrations : {expired} inscription(s) expirée(s)")
        return expired
