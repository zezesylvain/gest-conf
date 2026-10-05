"""Classes de base des commandes ``manage.py`` (règle n° 9, plan L1 §8.2 et §9.4)."""

from __future__ import annotations

import getpass
import time
from typing import Any

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.core.actor import Actor
from apps.core.locking import command_lock
from apps.core.models import CronHeartbeat, HeartbeatStatus

HEARTBEAT_ERROR_MAX_LENGTH = 2000


def command_actor() -> Actor:
    """Acteur d'une commande lancée par l'opérateur : ``cli:<utilisateur système>``."""
    try:
        user = getpass.getuser()
    except Exception:  # aucun utilisateur résolu (conteneur sans entrée passwd)
        user = "inconnu"
    return Actor.command(f"cli:{user}"[:64])


class LockedCommand(BaseCommand):
    """Commande cron idempotente, verrouillée et supervisée.

    - **Verrou** exclusif non bloquant (``apps.core.locking``) : si une autre
      exécution est en cours, la commande sort sans erreur (code 0).
    - **Battement de cœur** (``CronHeartbeat``) au début et à la fin : durée,
      nombre d'éléments traités, statut, date du dernier succès (``/health``).
    - Une erreur est journalisée dans le battement de cœur, signalée aux
      opérateurs (D17) puis propagée (code de sortie non nul, visible dans le
      journal du cron).

    Les sous-classes implémentent ``run()``, qui renvoie le nombre d'éléments traités.
    """

    #: Nom du verrou et du battement de cœur ; par défaut, le nom de la commande.
    lock_name: str = ""

    def get_lock_name(self) -> str:
        return self.lock_name or self.__module__.rsplit(".", 1)[-1]

    def run(self, *args: Any, **options: Any) -> int:
        raise NotImplementedError

    def handle(self, *args: Any, **options: Any) -> None:
        name = self.get_lock_name()
        with command_lock(name) as acquired:
            if not acquired:
                self.stdout.write(f"{name} : une autre exécution est en cours, rien à faire.")
                return
            self._run_with_heartbeat(name, *args, **options)

    def _run_with_heartbeat(self, name: str, *args: Any, **options: Any) -> None:
        started = timezone.now()
        CronHeartbeat.objects.update_or_create(
            name=name,
            defaults={"last_started_at": started, "last_status": HeartbeatStatus.RUNNING},
        )
        clock = time.monotonic()
        try:
            processed = self.run(*args, **options) or 0
        except Exception as exc:
            error = f"{type(exc).__module__}.{type(exc).__qualname__}"
            CronHeartbeat.objects.filter(name=name).update(
                last_finished_at=timezone.now(),
                last_status=HeartbeatStatus.ERROR,
                last_duration_ms=int((time.monotonic() - clock) * 1000),
                last_error=error[:HEARTBEAT_ERROR_MAX_LENGTH],
            )
            from apps.core.alerts import notify_operators

            notify_operators("Commande cron en erreur", {"commande": name, "erreur": error})
            raise
        finished = timezone.now()
        CronHeartbeat.objects.filter(name=name).update(
            last_finished_at=finished,
            last_success_at=finished,
            last_status=HeartbeatStatus.OK,
            last_duration_ms=int((time.monotonic() - clock) * 1000),
            processed_count=processed,
            last_error="",
        )
