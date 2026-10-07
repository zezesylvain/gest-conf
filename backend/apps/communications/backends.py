"""Backend d'e-mail de production sans fournisseur déclaré, et garde de démarrage (D10).

En production (``config/settings/prod.py``) :

- un fournisseur **déclaré mais incomplet** (``GESTCONF_EMAIL_PROVIDER`` posé, clé ou
  expéditeur manquant) fait échouer le chargement des réglages : aucun processus ne
  démarre (Passenger, cron, ``manage.py``) ;
- **aucun fournisseur déclaré** : les réglages se chargent, pour que ``manage.py check``,
  ``migrate`` et ``createcachetable`` restent utilisables pendant l'installation ; mais
  l'application web refuse de démarrer (``require_email_provider``, appelée par
  ``config/wsgi.py``) et tout envoi échoue explicitement (``UnconfiguredEmailBackend``),
  au lieu de tenter en silence un serveur SMTP local.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMessage
from django.core.mail.backends.base import BaseEmailBackend

MISSING_PROVIDER_MESSAGE = (
    "Aucun fournisseur d'e-mails configuré : renseigner GESTCONF_EMAIL_PROVIDER (brevo, "
    "mailjet ou smtp) et ses clés dans le .env de production (voir .env.example)."
)


class UnconfiguredEmailBackend(BaseEmailBackend):
    """Refuse tout envoi avec un message explicite (la tâche est reprise, puis en échec)."""

    def send_messages(self, email_messages: Sequence[EmailMessage]) -> int:
        raise ImproperlyConfigured(MISSING_PROVIDER_MESSAGE)


def require_email_provider() -> None:
    """Garde de démarrage de l'application web en production (``config/wsgi.py``)."""
    if settings.GESTCONF_EMAIL_PROVIDER_REQUIRED and not settings.GESTCONF_EMAIL_PROVIDER:
        raise ImproperlyConfigured(MISSING_PROVIDER_MESSAGE)
