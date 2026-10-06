"""Expiration des commandes impayées à l'échéance (plan L6, J5), lancée par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand


class Command(LockedCommand):
    help = (
        "Fait expirer les inscriptions en attente dont l'échéance de paiement est passée "
        "(places d'options et codes promo rendus, e-mail au participant) et prépare les "
        "séries de facturation de l'année. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        from apps.conferences.models import Edition, EditionStatus
        from apps.payments.services.documents import prepare_series
        from apps.registrations.services.orders import expire_overdue

        expired = expire_overdue()
        # Compteurs de facturation créés hors contention (verrous d'intervalle de MariaDB).
        for edition in Edition.objects.exclude(status=EditionStatus.ARCHIVED):
            prepare_series(edition)
        if options["verbosity"] >= 1:
            self.stdout.write(f"expire_registrations : {expired} inscription(s) expirée(s)")
        return expired
