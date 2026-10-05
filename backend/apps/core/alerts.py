"""Alertes minimales aux opérateurs (décision D17, plan L1 §4.10).

Pas de Sentry (transfert de données à un tiers, reporté en L9) ni
d'``AdminEmailHandler`` de Django, qui joint le détail de la requête (en-têtes,
cookies, corps, variables). Une alerte ne contient que :

- la nature de l'incident (type d'exception, tâche, commande) ;
- la route (motif d'URL résolu, jamais le chemin brut, qui pourrait porter un
  jeton), la méthode et le statut HTTP ;
- l'identifiant de requête, pour retrouver le détail dans le journal du serveur.

Envoi **direct**, sans passer par la file : une alerte doit partir même quand la
base ou la file est en panne. Volume plafonné par heure (cache partagé), pour
qu'une erreur répétée n'épuise pas le quota du fournisseur d'e-mails.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from django.conf import settings
from django.core.cache import cache
from django.core.mail import mail_admins
from django.utils import timezone

logger = logging.getLogger(__name__)

ALERT_VALUE_MAX_LENGTH = 200


def _within_hourly_budget() -> bool:
    """Compteur horaire partagé entre processus ; en cas d'erreur du cache, on envoie."""
    key = f"operator_alerts:{timezone.now():%Y%m%d%H}"
    try:
        cache.add(key, 0, timeout=3600)
        count = cache.incr(key)
    except Exception:
        logger.warning("Compteur d'alertes indisponible ; alerte envoyée sans plafond")
        return True
    return count <= settings.GESTCONF_OPERATOR_ALERTS_PER_HOUR


def notify_operators(subject: str, details: Mapping[str, str]) -> bool:
    """Envoie une alerte courte aux opérateurs (``ADMINS``) ; renvoie vrai si elle est partie.

    ``details`` ne doit contenir **aucune donnée personnelle** ni secret : nature
    de l'incident et identifiants techniques seulement. Ne lève jamais.
    """
    if not settings.ADMINS:
        return False
    if not _within_hourly_budget():
        logger.warning("Plafond horaire des alertes atteint ; alerte non envoyée : %s", subject)
        return False
    lines = [f"{name} : {str(value)[:ALERT_VALUE_MAX_LENGTH]}" for name, value in details.items()]
    lines += ["", f"Version : {settings.GESTCONF_RELEASE}", f"Date (UTC) : {timezone.now():%c}"]
    try:
        mail_admins(subject, "\n".join(lines), fail_silently=False)
    except Exception:
        logger.exception("Envoi de l'alerte aux opérateurs impossible")
        return False
    return True


class OperatorAlertHandler(logging.Handler):
    """Gestionnaire de journalisation branché sur ``django.request`` (erreurs 5xx).

    Remplace ``AdminEmailHandler`` : n'extrait de l'enregistrement que le type
    d'exception, la route, la méthode, le statut et l'identifiant de requête.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            details = {"exception": "-"}
            if record.exc_info and record.exc_info[0] is not None:
                exc_type = record.exc_info[0]
                details["exception"] = f"{exc_type.__module__}.{exc_type.__qualname__}"
            request = getattr(record, "request", None)
            if request is not None:
                match = getattr(request, "resolver_match", None)
                details["route"] = match.route if match is not None else "(non résolue)"
                details["méthode"] = getattr(request, "method", "") or "-"
                details["requête"] = getattr(request, "request_id", "") or "-"
            status_code = getattr(record, "status_code", None)
            if status_code is not None:
                details["statut"] = str(status_code)
            notify_operators("Erreur serveur", details)
        except Exception:
            self.handleError(record)
