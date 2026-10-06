"""Réconciliation des paiements en ligne (plan L6, J6 ; RG-15), lancée par le cron."""

from __future__ import annotations

from typing import Any

from apps.core.management.base import LockedCommand


class Command(LockedCommand):
    help = (
        "Interroge le fournisseur sur les paiements en ligne en cours (notification perdue ou "
        "en retard), abandonne les tentatives trop anciennes et crée les compteurs de "
        "facturation de l'année. Idempotente et verrouillée."
    )

    def run(self, *args: Any, **options: Any) -> int:
        from apps.conferences.models import Edition, EditionStatus
        from apps.payments.services.documents import prepare_series
        from apps.payments.services.online import sync_payments

        # Compteurs de facturation créés hors contention (verrous d'intervalle de MariaDB).
        for edition in Edition.objects.exclude(status=EditionStatus.ARCHIVED):
            prepare_series(edition)
        counts = sync_payments()
        if options["verbosity"] >= 1:
            self.stdout.write(
                "sync_payments : {checked} interrogé(s), {errors} erreur(s), "
                "{abandoned} abandonné(s)".format(**counts)
            )
        return counts["checked"]
