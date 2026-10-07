"""Alerte minimale aux opérateurs (décision D17, plan L1 §2).

Deux sources :

- ``OperatorAlertHandler``, gestionnaire de journalisation branché sur ``django.request`` :
  une exception non rattrapée pendant une requête (erreur 500) envoie un e-mail ;
- ``send_operator_alert``, appelée directement, par exemple par ``run_jobs`` pour une
  tâche en échec définitif.

**Contenu minimal.** Type d'exception, chemin (sans la chaîne de requête), méthode,
identifiant de requête, heure UTC et version déployée. **Jamais** le corps, les en-têtes,
les cookies, les paramètres, la trace d'appels ni le message de l'exception (qui peut
contenir une donnée personnelle) : le détail reste dans le journal du serveur, que
l'identifiant de requête permet de retrouver.

**Pourquoi pas ``AdminEmailHandler``.** Le gestionnaire de Django joint le rapport
d'erreur complet : représentation de la requête (en-têtes, cookies, paramètres GET et
POST, ``META``), trace d'appels avec les variables locales (données personnelles,
jetons), en HTML si ``include_html``. Il n'a pas de plafond d'envoi et lit ``ADMINS``.
Ce module n'en reprend que le principe (un gestionnaire de journalisation).

**Indépendance vis-à-vis de la base.** L'alerte ne passe pas par la file (``Job``,
``OutboxEmail``) : la base peut être la cause de l'erreur. Elle part directement par
``EMAIL_BACKEND`` (Brevo, Mailjet ou SMTP : aucun accès à la base), avec le délai réseau
court de la voie rapide. Le plafond (``GESTCONF_OPERATOR_ALERTS_PER_HOUR``, 10 par défaut)
est tenu dans un petit fichier verrouillé par ``flock`` sous ``GESTCONF_LOCK_DIR``,
commun aux processus Passenger et au cron ; si ce fichier est inutilisable, le plafond
est tenu en mémoire, par processus. Aucune erreur de l'alerte ne remonte : elle est
écrite sur la sortie d'erreur (journal de Passenger), et la réponse 500 part normalement.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import threading
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)

ALERT_WINDOW_SECONDS = 3600
STATE_FILE_NAME = "operator-alerts.json"
PATH_MAX_LENGTH = 200

_memory_lock = threading.Lock()
_memory_state: dict[str, list[float] | int] = {"sent": [], "suppressed": 0}
_reentrancy = threading.local()


def _printable(value: str, limit: int) -> str:
    """Caractères de contrôle échappés (aucune ligne forgée dans l'e-mail), longueur bornée.

    Les lettres accentuées restent lisibles ; un saut de ligne devient « \\n ».
    """
    escaped = "".join(char if char.isprintable() else repr(char)[1:-1] for char in value)
    return escaped[:limit]


def _update_state(state: dict, now: float, limit: int) -> tuple[bool, int]:
    """Applique le plafond à ``state`` (modifié en place) ; renvoie (permis, alertes retenues)."""
    sent = [stamp for stamp in state.get("sent", []) if now - stamp < ALERT_WINDOW_SECONDS]
    suppressed = int(state.get("suppressed", 0))
    if len(sent) >= limit:
        state.update(sent=sent, suppressed=suppressed + 1)
        return False, suppressed + 1
    state.update(sent=[*sent, now], suppressed=0)
    return True, suppressed


def _take_slot_from_file(path: Path, now: float, limit: int) -> tuple[bool, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(fd, "r+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            state = json.loads(handle.read() or "{}")
        except ValueError:
            state = {}
        if not isinstance(state, dict):
            state = {}
        result = _update_state(state, now, limit)
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(state))
    return result


def take_alert_slot(now: float | None = None) -> tuple[bool, int]:
    """Réserve une alerte dans le plafond horaire.

    Renvoie ``(permis, retenues)`` : si permis, ``retenues`` est le nombre d'alertes
    supprimées par le plafond depuis la précédente alerte envoyée.
    """
    now = time.time() if now is None else now
    limit = settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR
    if limit <= 0:
        return False, 0
    try:
        return _take_slot_from_file(Path(settings.GESTCONF_LOCK_DIR) / STATE_FILE_NAME, now, limit)
    except OSError:
        with _memory_lock:
            return _update_state(_memory_state, now, limit)


def reset_memory_state() -> None:
    """Oublie le plafond tenu en mémoire (tests)."""
    with _memory_lock:
        _memory_state.update(sent=[], suppressed=0)


def send_operator_alert(subject: str, lines: Sequence[tuple[str, str]]) -> bool:
    """Envoie une alerte aux adresses ``GESTCONF_OPERATOR_EMAILS``, dans la limite du plafond.

    ``subject`` et ``lines`` (libellé, valeur) ne doivent contenir aucune donnée
    personnelle. Ne lève jamais d'exception ; renvoie ``True`` si l'e-mail est parti.
    """
    recipients = list(settings.GESTCONF_OPERATOR_EMAILS)
    if not recipients or getattr(_reentrancy, "active", False):
        return False
    _reentrancy.active = True
    try:
        allowed, suppressed = take_alert_slot()
        if not allowed:
            return False
        from django.core.mail import EmailMessage, get_connection

        with translation.override(settings.LANGUAGE_CODE):
            body_lines = [f"{label} : {value}" for label, value in lines]
            if suppressed:
                body_lines.append(
                    _("Alertes retenues par le plafond horaire depuis la précédente : %(count)s")
                    % {"count": suppressed}
                )
            body_lines.append("")
            body_lines.append(
                _("Détail dans le journal du serveur (rechercher l'identifiant de requête).")
            )
            full_subject = f"[{settings.GESTCONF_SITE_NAME}] {subject}"
        connection = get_connection(timeout=settings.GESTCONF_EMAIL_FAST_PATH_TIMEOUT)
        message = EmailMessage(
            subject=_printable(full_subject, 200),
            body="\n".join(body_lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
            connection=connection,
        )
        return message.send() == 1
    except Exception:
        # Ni la base ni le fournisseur ne doivent transformer une alerte en nouvelle erreur.
        logger.exception("Alerte aux opérateurs impossible à envoyer.")
        return False
    finally:
        _reentrancy.active = False


def alert_lines_for_request_error(record: logging.LogRecord) -> list[tuple[str, str]]:
    """Lignes d'une alerte d'erreur serveur : rien de la requête au-delà du chemin."""
    exc_type = record.exc_info[0] if record.exc_info else None
    request = getattr(record, "request", None)
    at = datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="seconds")
    return [
        (_("Exception"), exc_type.__name__ if exc_type is not None else "-"),
        (_("Méthode"), _printable(getattr(request, "method", "") or "-", 10)),
        (_("Chemin"), _printable(getattr(request, "path", "") or "-", PATH_MAX_LENGTH)),
        (_("Identifiant de requête"), getattr(request, "request_id", "") or "-"),
        (_("Heure (UTC)"), at),
        (_("Version"), settings.GESTCONF_RELEASE),
    ]


class OperatorAlertHandler(logging.Handler):
    """Gestionnaire de journalisation : une alerte par exception non rattrapée d'une requête.

    Branché sur ``django.request`` (``LOGGING``) au niveau ``ERROR``. Seuls les
    enregistrements portant une exception (``exc_info``) déclenchent une alerte : une
    réponse 5xx volontaire (``/health`` en 503) n'en déclenche pas.
    """

    def __init__(self, level: int = logging.ERROR) -> None:
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if not record.exc_info or record.exc_info[0] is None:
                return
            with translation.override(settings.LANGUAGE_CODE):
                exc_name = record.exc_info[0].__name__
                subject = _("Erreur serveur : %(exception)s") % {"exception": exc_name}
                lines = alert_lines_for_request_error(record)
            send_operator_alert(subject, lines)
        except Exception:
            self.handleError(record)
