"""Sessions pré-établies du test de charge (plan L9, S5) : ``manage.py loadtest_sessions``.

    python manage.py loadtest_sessions --confirm-fictitious --output ~/gestconf-sessions.json
    python manage.py loadtest_sessions --revoke ~/gestconf-sessions.json

Comptes fictifs seulement ; refusée sans ``--confirm-fictitious`` ou dès que la base contient
des données réelles. Le fichier contient des cookies de session : 0600, hors du dépôt et de
la racine web, supprimé après le test (voir ``loadtest/README.md``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.core.audit import record
from apps.core.management.base import command_actor
from apps.qa.fictitious import CONFIRM_OPTION, ensure_fictitious_only
from apps.qa.sessions import SessionFileError, revoke_sessions, write_sessions

DEFAULTS = {"committee": 2, "reviewer": 60, "author": 100, "participant": 150, "newcomer": 100}


class Command(BaseCommand):
    help = "Ouvre des sessions pour les comptes fictifs du test de charge (fichier JSON)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(CONFIRM_OPTION, action="store_true", dest="confirmed")
        parser.add_argument("--output", type=Path, help="Fichier JSON à créer (0600).")
        parser.add_argument("--revoke", type=Path, help="Supprime les sessions du fichier.")
        for name, default in DEFAULTS.items():
            parser.add_argument(f"--{name}s", type=int, default=default, dest=name)

    def handle(self, *args: Any, **options: Any) -> None:
        if options["revoke"]:
            count = revoke_sessions(options["revoke"])
            record("qa.loadtest_sessions_revoked", actor=command_actor(), after={"count": count})
            self.stdout.write(f"loadtest_sessions : {count} sessions supprimées.")
            return
        if not options["output"]:
            raise CommandError("Préciser --output (ou --revoke).")
        ensure_fictitious_only(confirmed=options["confirmed"])
        counts = {name: options[name] for name in DEFAULTS}
        try:
            opened = write_sessions(options["output"], counts)
        except SessionFileError as error:
            raise CommandError(str(error)) from error
        record("qa.loadtest_sessions_opened", actor=command_actor(), after={"counts": opened})
        for name, count in opened.items():
            self.stdout.write(f"  {name} : {count}")
        self.stdout.write(
            f"loadtest_sessions : {sum(opened.values())} sessions dans {options['output']} "
            "(cookies de session : ne pas versionner, supprimer après le test)."
        )
