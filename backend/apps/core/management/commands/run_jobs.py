"""Exécute la file de tâches (cron, plan L1 §8.2). Exemple de crontab :

    */5 * * * *  <app>/deploy/cron.sh run_jobs --max-seconds 240

Déroulement : verrou de commande et battement de cœur (``LockedCommand``) ; reprise des
tâches au bail expiré ; purges de sécurité fréquentes (entrées expirées des deux tables de
cache, corps des e-mails sensibles) ; boucle sur les tâches éligibles dans le budget de
temps. Non audité à chaque passage : la trace est le battement de cœur (arbitrage L1.2).
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import CommandError, CommandParser
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from apps.core.actor import Actor
from apps.core.jobs import process_jobs, recover_stale_jobs, worker_id
from apps.core.management.base import CommandResult, LockedCommand
from apps.core.retention import run_rules

# Part de l'intervalle du cron laissée à la boucle par défaut : une tâche commencée juste
# avant l'échéance (un envoi d'e-mail, borné par son délai réseau) finit avant le passage
# suivant, qui trouverait sinon le verrou pris.
DEFAULT_BUDGET_RATIO = 0.8


def default_max_seconds() -> int:
    return max(1, int(settings.GESTCONF_CRON_INTERVAL_SECONDS * DEFAULT_BUDGET_RATIO))


class Command(LockedCommand):
    help = gettext_lazy("Exécute les tâches en attente (à lancer par le cron).")

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--max-seconds",
            type=int,
            default=None,
            help=_(
                "Budget de temps : aucune tâche n'est commencée au-delà (par défaut, 80 %% de "
                "GESTCONF_CRON_INTERVAL_SECONDS). À garder inférieur à l'intervalle du cron."
            ),
        )

    def run(self, **options: Any) -> CommandResult:
        max_seconds = options["max_seconds"]
        if max_seconds is None:
            max_seconds = default_max_seconds()
        if max_seconds <= 0:
            raise CommandError(_("--max-seconds doit être strictement positif."))
        now = timezone.now()
        recovered = recover_stale_jobs(now=now)
        purges = run_rules(
            now, actor=Actor.system("job:run_jobs"), enforce_legal=False, only_with_jobs=True
        )
        processed = process_jobs(max_seconds=max_seconds, worker=worker_id())
        errors = sorted(name for name, entry in purges.items() if "error" in entry)
        self.stdout.write(
            _(
                "Tâches exécutées : %(processed)s ; reprises après bail expiré : %(requeued)s ; "
                "passées en échec : %(failed)s."
            )
            % {"processed": processed, **recovered}
        )
        summary = {"recovered": recovered, "purges": purges}
        return CommandResult(
            processed=processed,
            summary=summary,
            # Une purge en erreur est signalée sans faire échouer le passage : les tâches,
            # elles, ont été traitées (le battement de cœur reste un succès).
            error=_("Purges en erreur : %(rules)s") % {"rules": ", ".join(errors)}
            if errors
            else "",
        )
