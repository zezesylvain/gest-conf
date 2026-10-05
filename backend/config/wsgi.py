"""Point d'entrée WSGI (utilisé par Passenger en production et par runserver)."""

import os

from django.core.wsgi import get_wsgi_application

from config.mount import MountPrefixMiddleware

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = MountPrefixMiddleware(
    get_wsgi_application(),
    prefix=os.environ.get("GESTCONF_URL_PREFIX", "/api"),
)
