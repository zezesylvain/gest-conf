"""Classe de base des commandes d'exploitation (plan L1 §8.2, §9.4).

``LockedCommand`` :

- prend le verrou exclusif de la commande (``apps.core.locks``) ; s'il est déjà pris,
  la commande s'arrête **sans erreur** (code 0) : le passage suivant du cron reprendra ;
- note un battement de cœur au début et à la fin (``CronHeartbeat``), sauf pour les
  commandes d'opérateur qui le désactivent (``heartbeat_enabled = False``) ;
- appelle ``run(**options)``, à définir par chaque commande.

Les commandes d'opérateur sont auditées (``actor_kind=command``) par leur propre code,
avec ``command_actor()`` ; un motif est exigé (``--reason``) quand l'action est sensible.
Les commandes lancées par le cron ne sont pas auditées à chaque passage : leur trace est
le battement de cœur (arbitrage L1.2).
"""

from __future__ import annotations

import getpass
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.translation import gettext as _

from apps.core.actor import LABEL_MAX_LENGTH, Actor
from apps.core.heartbeat import beat_finish, beat_start
from apps.core.jobs import safe_error_text
from apps.core.locks import CommandLock

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Bilan d'un passage, repris dans le battement de cœur (sans donnée personnelle)."""

    processed: int = 0
    summary: dict[str, Any] | None = None
    error: str = ""
    succeeded: bool = True


def command_actor() -> Actor:
    """Acteur d'une commande d'opérateur : ``cli:<utilisateur système>``."""
    try:
        user = getpass.getuser()
    except (KeyError, OSError):
        user = ""
    printable = "".join(char for char in user if char.isprintable() and not char.isspace())
    return Actor.command(f"cli:{printable or 'unknown'}"[:LABEL_MAX_LENGTH])


def add_reason_argument(parser: CommandParser, *, required_for: str = "") -> None:
    help_text = _("Motif de l'opération, conservé dans le journal d'audit.")
    if required_for:
        help_text += " " + _("Obligatoire pour %(option)s.") % {"option": required_for}
    parser.add_argument("--reason", default="", help=help_text)


def require_reason(options: dict[str, Any]) -> str:
    """Motif non vide, ou ``CommandError`` avant toute modification (RG-17)."""
    reason = (options.get("reason") or "").strip()
    if not reason:
        raise CommandError(_("Motif obligatoire pour cette opération sensible : --reason."))
    return reason


class LockedCommand(BaseCommand):
    """Commande verrouillée, avec battement de cœur (voir le docstring du module)."""

    heartbeat_enabled: ClassVar[bool] = True

    @property
    def command_name(self) -> str:
        return type(self).__module__.rsplit(".", 1)[-1]

    def run(self, **options: Any) -> CommandResult | None:
        raise NotImplementedError

    def handle(self, *args: Any, **options: Any) -> None:
        lock = CommandLock(self.command_name, Path(settings.GESTCONF_LOCK_DIR))
        if not lock.acquire():
            self.stdout.write(
                _("« %(command)s » est déjà en cours d'exécution : rien à faire.")
                % {"command": self.command_name}
            )
            return
        try:
            if self.heartbeat_enabled:
                self._run_with_heartbeat(**options)
            else:
                self.run(**options)
        finally:
            lock.release()

    def _run_with_heartbeat(self, **options: Any) -> None:
        started_at = beat_start(self.command_name)
        try:
            result = self.run(**options) or CommandResult()
        except BaseException as exc:
            try:
                beat_finish(
                    self.command_name,
                    started_at=started_at,
                    succeeded=False,
                    error=safe_error_text(exc),
                )
            except Exception:
                # Base injoignable : l'erreur d'origine compte davantage que le battement.
                logger.exception("Battement de cœur de fin impossible (%s).", self.command_name)
            raise
        beat_finish(
            self.command_name,
            started_at=started_at,
            succeeded=result.succeeded,
            processed=result.processed,
            error=result.error,
            summary=result.summary,
        )
        if not result.succeeded:
            raise CommandError(result.error or _("Passage en échec."))
