"""Configuration de production (o2switch).

Variables d'environnement obligatoires : DJANGO_SECRET_KEY, DJANGO_ALLOWED_HOSTS,
DJANGO_CSRF_TRUSTED_ORIGINS, DATABASE_URL, GESTCONF_EMAIL_BACKEND, DEFAULT_FROM_EMAIL,
GESTCONF_PUBLIC_URL, GESTCONF_MFA_ENCRYPTION_KEYS.
Voir .env.example.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

SECRET_KEY = env.str("DJANGO_SECRET_KEY")
# Rotation de la clé (revue de sécurité L9.5, deploy/README.md) : l'ancienne clé, placée ici
# le temps que les sessions et les liens signés qu'elle a produits expirent, est encore
# acceptée en vérification ; elle ne signe plus rien.
SECRET_KEY_FALLBACKS = env.list("DJANGO_SECRET_KEY_FALLBACKS", default=[])
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
# Ex. https://conference.exemple.org (nécessaire si Passenger ne signale pas
# correctement HTTPS à Django : la vérification de l'en-tête Origin échouerait).
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

DATABASES = {"default": database_from_env()}

# E-mails : fournisseur obligatoire (D10), jamais le backend « console » par défaut.
EMAIL_BACKEND = env.str("GESTCONF_EMAIL_BACKEND")
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL")
SMTP_EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
if EMAIL_BACKEND == SMTP_EMAIL_BACKEND:
    # SMTP de l'hébergement (D10 amendée) : envoi authentifié et chiffré seulement.
    if not (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD) or EMAIL_HOST == "localhost":
        raise ImproperlyConfigured(
            "SMTP : EMAIL_HOST, EMAIL_HOST_USER et EMAIL_HOST_PASSWORD sont obligatoires."
        )
    if EMAIL_USE_SSL == EMAIL_USE_TLS:
        raise ImproperlyConfigured("SMTP : EMAIL_USE_SSL (465) ou EMAIL_USE_TLS (587), un seul.")

# Liens des e-mails (vérification, réinitialisation) : domaine officiel en HTTPS,
# obligatoire (lu par base.py, qui construit HEADLESS_FRONTEND_URLS).
if not env.str("GESTCONF_PUBLIC_URL", default="").startswith("https://"):
    raise ImproperlyConfigured("GESTCONF_PUBLIC_URL (https://…) est obligatoire en production.")

# Chiffrement du secret TOTP (plan L1 §4.10) : sans clé, aucune 2FA ne pourrait être activée.
if not GESTCONF_MFA_ENCRYPTION_KEYS:
    raise ImproperlyConfigured("GESTCONF_MFA_ENCRYPTION_KEYS est obligatoire en production.")

# Paiement en ligne (plan L6, J6) : jamais le fournisseur factice en production, sauf sur une
# recette déclarée ; CinetPay exige ses identifiants (règle n° 11 : dans l'environnement).
if GESTCONF_PAYMENT_PROVIDER not in ("", "fake", "cinetpay"):
    raise ImproperlyConfigured("GESTCONF_PAYMENT_PROVIDER : vide, « fake » ou « cinetpay ».")
if GESTCONF_PAYMENT_PROVIDER == "fake" and not GESTCONF_ALLOW_FAKE_PAYMENTS:
    raise ImproperlyConfigured(
        "Fournisseur de paiement factice en production : réservé à une recette "
        "(GESTCONF_ALLOW_FAKE_PAYMENTS=true)."
    )
if GESTCONF_PAYMENT_PROVIDER == "cinetpay" and not (CINETPAY_API_KEY and CINETPAY_API_PASSWORD):
    raise ImproperlyConfigured("CINETPAY_API_KEY et CINETPAY_API_PASSWORD sont obligatoires.")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
# Les sous-domaines de l'offre ne sont pas connus (étude §11.2) : désactivé par défaut.
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)

# La redirection HTTP -> HTTPS est faite par cPanel (« Forcer la redirection HTTPS »,
# deploy/README.md), vérifiée par deploy/smoke-test.sh. L'activer aussi
# dans Django n'est sûr que si Passenger transmet bien le schéma HTTPS :
# à vérifier avec le champ « secure » de /api/v1/health avant de l'activer.
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

SILENCED_SYSTEM_CHECKS = [
    # W005 : includeSubDomains, cf. ci-dessus (choix explicite, configurable).
    "security.W005",
    # W008 : redirection HTTPS assurée par cPanel, cf. ci-dessus.
    "security.W008",
    # W021 : le préchargement HSTS engage durablement le domaine et ses
    # sous-domaines ; décision à prendre avec le commanditaire.
    "security.W021",
]
