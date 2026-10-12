"""Données de volume du test de charge (plan L9, S6) : ``manage.py seed_volume``.

Refusée sans ``--confirm-fictitious`` ou dès que la base contient des données réelles.
Avant : ``backup_db`` ; après le test : restauration de cette sauvegarde dans une base neuve
(``restore_db``). Voir ``docs/L9-runbook-o2switch.md``.
"""

from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.conferences.models import Conference
from apps.core.audit import record
from apps.core.management.base import command_actor
from apps.qa.fictitious import CONFIRM_OPTION, FICTITIOUS_CONFERENCE, ensure_fictitious_only
from apps.qa.volume import seed_volume


class Command(BaseCommand):
    help = "Crée la conférence fictive du test de charge (volume de l'étude, §12)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(CONFIRM_OPTION, action="store_true", dest="confirmed")
        parser.add_argument("--submissions", type=int, default=600)
        parser.add_argument("--reviewers", type=int, default=100)
        parser.add_argument("--participants", type=int, default=1500)
        parser.add_argument("--drafts", type=int, default=300)

    def handle(self, *args: Any, **options: Any) -> None:
        ensure_fictitious_only(confirmed=options["confirmed"])
        if Conference.objects.filter(slug=FICTITIOUS_CONFERENCE).exists():
            raise CommandError("La conférence fictive existe déjà : restaurer la sauvegarde.")
        started = time.monotonic()
        report = seed_volume(
            submissions=options["submissions"],
            reviewers=options["reviewers"],
            participants=options["participants"],
            drafts=options["drafts"],
            progress=lambda message: self.stdout.write(f"seed_volume : {message}…"),
        )
        elapsed = time.monotonic() - started
        record(
            "qa.volume_seeded",
            actor=command_actor(),
            after={"editions": report.editions, "counts": report.counts},
        )
        self.stdout.write(f"seed_volume : terminé en {elapsed:.0f} s.")
        for name, value in report.counts.items():
            self.stdout.write(f"  {name} : {value}")
        self.stdout.write(f"  éditions : {report.editions}")
        self.stdout.write(f"  comité : {report.committee}")
        # Affichés une seule fois : comptes fictifs d'une base qui sera restaurée ensuite.
        self.stdout.write(f"  mot de passe des comptes fictifs : {report.password}")
        self.stdout.write(f"  secret TOTP (comité et relecteurs) : {report.totp_secret}")
