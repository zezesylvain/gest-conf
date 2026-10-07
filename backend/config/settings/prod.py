"""Configuration de production (o2switch).

Variables d'environnement obligatoires : DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
DJANGO_CSRF_TRUSTED_ORIGINS, DATABASE_URL ; pour servir le site, le fournisseur d'e-mails
(GESTCONF_EMAIL_PROVIDER, ses clés et DEFAULT_FROM_EMAIL). Voir .env.example.
"""

from .base import *

DEBUG = False

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
# Ex. https://conference.exemple.org (nécessaire si Passenger ne signale pas
# correctement HTTPS à Django : la vérification de l'en-tête Origin échouerait).
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

DATABASES = {"default": database_from_env()}

# E-mails (D10) : fournisseur déclaré mais incomplet = échec immédiat du chargement des
# réglages (ImproperlyConfigured) ; aucun fournisseur = réglages chargés (check, migrate,
# createcachetable restent possibles), mais l'application web refuse de démarrer
# (apps.communications.backends.require_email_provider, appelée par config/wsgi.py) et
# tout envoi échoue explicitement. Clés lues dans l'environnement, jamais dans le dépôt.
globals().update(email_settings_from_env(env, timeout=GESTCONF_EMAIL_TIMEOUT))
GESTCONF_EMAIL_PROVIDER_REQUIRED = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
# Les sous-domaines de l'offre ne sont pas connus (étude §11.2) : désactivé par défaut.
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)

# La redirection HTTP -> HTTPS est faite par Apache (.htaccess). L'activer aussi
# dans Django n'est sûr que si Passenger transmet bien le schéma HTTPS :
# à vérifier avec le champ « secure » de /api/v1/health avant de l'activer.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

SILENCED_SYSTEM_CHECKS = [
    # W005 : includeSubDomains, cf. ci-dessus (choix explicite, configurable).
    "security.W005",
    # W008 : redirection HTTPS assurée par Apache, cf. ci-dessus.
    "security.W008",
    # W021 : le préchargement HSTS engage durablement le domaine et ses
    # sous-domaines ; décision à prendre avec le commanditaire.
    "security.W021",
]
