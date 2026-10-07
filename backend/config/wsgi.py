"""Point d'entrée WSGI (utilisé par Passenger en production et par runserver)."""

import os

from django.core.wsgi import get_wsgi_application

from config.mount import MountPrefixMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

_django_application = get_wsgi_application()

# Production sans fournisseur d'e-mails : refus de démarrer, explicite (D10).
from apps.communications.backends import require_email_provider  # noqa: E402

require_email_provider()

application = MountPrefixMiddleware(
    _django_application,
    prefix=os.environ.get("GESTCONF_URL_PREFIX", "/api"),
)
