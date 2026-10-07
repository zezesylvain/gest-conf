"""Configuration commune à tous les environnements.

Toute valeur sensible ou propre à un environnement (secret, base de données,
hôtes autorisés) est lue dans les variables d'environnement ou dans un fichier
.env situé hors du dépôt (voir .env.example). Ne jamais committer de secret.
"""

import tomllib
from email.utils import parseaddr
from pathlib import Path
from typing import Any

import environ
import pymysql
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
_env_file = Path(env.str("GESTCONF_ENV_FILE", default=str(BASE_DIR / ".env")))
if _env_file.is_file():
    environ.Env.read_env(_env_file)

# Identifiant de la version déployée : fichier RELEASE écrit par deploy/deploy.sh.
_release_file = BASE_DIR / "RELEASE"
GESTCONF_RELEASE = env.str(
    "GESTCONF_RELEASE",
    default=_release_file.read_text().strip() if _release_file.is_file() else "dev",
)

# Version du projet : source unique, pyproject.toml (déployé avec le code). Reprise
# dans le schéma OpenAPI (SPECTACULAR_SETTINGS["VERSION"], plan L1 §9.5).
with (BASE_DIR / "pyproject.toml").open("rb") as _pyproject:
    GESTCONF_VERSION = tomllib.load(_pyproject)["project"]["version"]

# --- Applications ---------------------------------------------------------------
# « django.contrib.admin » est volontairement absent (règle n° 1 de CLAUDE.md) :
# toute opération passe par l'espace de gestion Angular ou par manage.py.
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "apps.core",
    "apps.accounts",
    "apps.communications",
]

MIDDLEWARE = [
    # En tête de liste : ces en-têtes sont posés sur toutes les réponses, y compris
    # celles produites par les middlewares suivants (refus CSRF, par exemple).
    "apps.core.middleware.RequestIdMiddleware",
    "apps.core.middleware.RobotsTagMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # Langue de la requête (en-tête Accept-Language) : messages d'erreur FR/EN.
    # Après SessionMiddleware, avant CommonMiddleware (documentation de Django).
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

# Les endpoints n'ont pas de barre oblique finale (ex. /api/v1/health) :
# pas de redirection automatique, qui casserait les requêtes POST.
APPEND_SLASH = False

# Gabarits des applications : page Swagger en développement (drf-spectacular) et gabarits
# d'e-mails du projet (apps/*/templates/, rendus sans requête ni processeur de contexte).
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

# --- Base de données (MariaDB) -------------------------------------------------
# PyMySQL (pur Python) remplace mysqlclient, dont la compilation n'est pas
# garantie sur l'hébergement mutualisé. Django 5.2 exige MariaDB >= 10.5.
pymysql.install_as_MySQLdb()

# Mode SQL imposé à chaque connexion (OPTIONS["init_command"], transmis tel quel à
# PyMySQL par le moteur MySQL de Django), pour ne pas dépendre du réglage du
# serveur o2switch, inconnu : en mode strict, une valeur trop longue lève une
# erreur au lieu d'être tronquée en silence (contrôle mysql.W002 de Django).
# Liste explicite et identique partout (CI, développement, production) :
# STRICT_TRANS_TABLES (strict), ERROR_FOR_DIVISION_BY_ZERO, NO_ENGINE_SUBSTITUTION
# (refuser une table créée hors InnoDB). Les autres modes éventuels du serveur
# (ANSI_QUOTES, ONLY_FULL_GROUP_BY...) sont ainsi neutralisés.
MARIADB_SQL_MODE = "STRICT_TRANS_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
MARIADB_INIT_COMMAND = f"SET SESSION sql_mode='{MARIADB_SQL_MODE}'"


def database_from_env(default: str | None = None) -> dict:
    """Construit la configuration de la base à partir de DATABASE_URL.

    Exemple : mysql://gestconf:motdepasse@localhost:3306/gestconf
    """
    config = env.db("DATABASE_URL") if default is None else env.db("DATABASE_URL", default=default)
    if config["ENGINE"] == "django.db.backends.mysql":
        config.setdefault("OPTIONS", {}).update(
            {"charset": "utf8mb4", "init_command": MARIADB_INIT_COMMAND}
        )
        config["TEST"] = {"CHARSET": "utf8mb4", "COLLATION": "utf8mb4_unicode_ci"}
    return config


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Authentification ---------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Internationalisation -------------------------------------------------------
LANGUAGE_CODE = "fr"
LANGUAGES = [("fr", "Français"), ("en", "English")]
USE_I18N = True
# Catalogues du projet (messages sources en français, catalogue « en ») : les .po
# ET les .mo sont versionnés, gettext n'étant pas garanti sur l'hébergement.
LOCALE_PATHS = [BASE_DIR / "locale"]
# Toutes les dates sont stockées en UTC ; la conversion dans le fuseau de
# l'édition se fait côté interface.
TIME_ZONE = "UTC"
USE_TZ = True

# --- Cache partagé -----------------------------------------------------------------
# Obligatoire (plan L1 §4.2) : les limites de débit et, plus tard, l'anti-rejeu
# TOTP passent par le cache. Le cache par défaut (mémoire locale) serait propre à
# chaque processus Passenger. Pas de Redis sur l'hébergement mutualisé : table en
# base, créée par « manage.py createcachetable » (pas par une migration).
#
# Au-delà de MAX_ENTRIES, Django supprime d'abord les entrées expirées, puis
# 1/CULL_FREQUENCY des clés restantes, par ordre alphabétique et sans distinguer
# leur rôle (compteurs de débit compris). 50 000 laisse une large marge en usage
# normal (la valeur par défaut, 300, purgerait des compteurs en service) ; le coût
# du COUNT(*) qui précède chaque écriture dépend du nombre réel de lignes, pas de
# ce plafond. CULL_FREQUENCY reste à 3 (valeur par défaut de Django) : 0 viderait
# tout le cache d'un coup, et une valeur plus grande purgerait moins à chaque fois
# mais plus souvent, chaque purge coûtant une requête de tri sur toute la table.
#
# Deux tables, créées toutes deux par « createcachetable » (qui parcourt CACHES) :
# - « default » (gestconf_cache) : clés de sécurité (limites de débit et anti-rejeu
#   TOTP d'allauth en L1.3 et L1.6), sonde /health ;
# - « throttle » (gestconf_throttle_cache) : compteurs des limites DRF seulement
#   (apps.core.throttling). Un attaquant peut multiplier les compteurs anonymes par
#   IP ; dans une table commune, la purge alphabétique effacerait alors d'abord les
#   clés « allauth… » et les compteurs « throttle_account_deletion_… » (risque R18).
_DATABASE_CACHE_OPTIONS = {"MAX_ENTRIES": 50000, "CULL_FREQUENCY": 3}
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "gestconf_cache",
        "OPTIONS": dict(_DATABASE_CACHE_OPTIONS),
    },
    "throttle": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "gestconf_throttle_cache",
        "OPTIONS": dict(_DATABASE_CACHE_OPTIONS),
    },
}

# --- CSRF -----------------------------------------------------------------------------
# Échec du contrôle CSRF hors DRF (vues Django ordinaires, dont allauth) : réponse
# JSON 403 « csrf_failed » au lieu de la page HTML de Django (plan L1 §4.6).
CSRF_FAILURE_VIEW = "apps.core.views.csrf_failure"

# --- Adresse IP du client ---------------------------------------------------------------
# Nombre de mandataires de confiance devant Django (plan L1 §4.2). 0 (défaut sûr) :
# REMOTE_ADDR seul, X-Forwarded-For ignoré car forgeable par le client. Valeur à
# mesurer sur o2switch (étape L1.0, endpoint /api/v1/diagnostics/request). Une seule
# source pour DRF (NUM_PROXIES), apps.core.http.client_ip() et, en L1.3, allauth.
GESTCONF_TRUSTED_PROXY_COUNT = env.int("GESTCONF_TRUSTED_PROXY_COUNT", default=0)
if GESTCONF_TRUSTED_PROXY_COUNT < 0:
    raise ImproperlyConfigured("GESTCONF_TRUSTED_PROXY_COUNT doit être positif ou nul.")

# Endpoint de diagnostic /api/v1/diagnostics/request (étape L1.0) : désactivé par
# défaut ; à n'activer que le temps d'une mesure.
GESTCONF_DIAGNOSTICS = env.bool("GESTCONF_DIAGNOSTICS", default=False)

# --- Tâches asynchrones et cron (plan L1 §8) ---------------------------------------------
# Intervalle du cron de run_jobs, en secondes (300 = toutes les 5 min, fréquence à
# confirmer sur o2switch, M01/H-6). /health signale « late » au-delà de 3 intervalles sans
# passage réussi, et le budget par défaut de run_jobs en vaut 80 %.
GESTCONF_CRON_INTERVAL_SECONDS = env.int("GESTCONF_CRON_INTERVAL_SECONDS", default=300)
if GESTCONF_CRON_INTERVAL_SECONDS <= 0:
    raise ImproperlyConfigured("GESTCONF_CRON_INTERVAL_SECONDS doit être strictement positif.")
# Dossier des verrous des commandes d'exploitation (flock) et de l'état du plafond des
# alertes. Dans le dossier de l'application, exclu du déploiement (rsync --exclude /tmp/).
GESTCONF_LOCK_DIR = Path(env.str("GESTCONF_LOCK_DIR", default=str(BASE_DIR / "tmp")))
# Purges du cadre légal (D15 : corps d'e-mails 30 j, métadonnées d'envoi 12 mois, contexte
# réseau de l'audit 6 mois, audit 3 ans, tâches terminées 30 j) : simulées tant que ce
# réglage est faux, le cadre légal (Q14) n'étant pas tranché. Les purges de sécurité sont
# toujours actives.
GESTCONF_RETENTION_ENFORCE = env.bool("GESTCONF_RETENTION_ENFORCE", default=False)

# --- E-mails (plan L1 §8.3, D10, D17) -------------------------------------------------------
# Nom du site, fixe, repris dans les gabarits d'e-mails (jamais une donnée de personne).
GESTCONF_SITE_NAME = env.str("GESTCONF_SITE_NAME", default="GEST-CONF")
# Expéditeur. En production, obligatoire dès qu'un fournisseur est déclaré (prod.py).
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="GEST-CONF <no-reply@localhost>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
# Backend par environnement : console (dev.py), locmem (test.py), fournisseur (prod.py).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# Délai réseau d'un envoi par le cron, en secondes : SMTP (EMAIL_TIMEOUT) et API HTTP
# d'anymail (ANYMAIL["REQUESTS_TIMEOUT"], 30 s par défaut dans anymail 15.2, lu dans
# anymail/backends/base_requests.py ; requests l'applique à la connexion et à la lecture).
GESTCONF_EMAIL_TIMEOUT = env.int("GESTCONF_EMAIL_TIMEOUT", default=10)
# Délai réseau de la voie rapide et des alertes aux opérateurs, pendant une requête HTTP :
# court, pour ne pas bloquer la réponse. Pire cas d'une requête : 3 envois (plafond par
# requête) fois (connexion + lecture), soit 18 s avec 3 s. Au-delà, l'envoi échoue et le cron
# le reprend (doublon possible si le fournisseur avait accepté, rare et assumé, §8.3).
GESTCONF_EMAIL_FAST_PATH_TIMEOUT = env.float("GESTCONF_EMAIL_FAST_PATH_TIMEOUT", default=3.0)
EMAIL_TIMEOUT = GESTCONF_EMAIL_TIMEOUT
ANYMAIL: dict[str, Any] = {"REQUESTS_TIMEOUT": GESTCONF_EMAIL_TIMEOUT}
# Plafond global d'envoi par heure (§4.7) : au-delà, les e-mails sont reportés en file.
GESTCONF_EMAIL_MAX_PER_HOUR = env.int("GESTCONF_EMAIL_MAX_PER_HOUR", default=300)
# Fournisseur (prod.py) : vide hors production.
GESTCONF_EMAIL_PROVIDER = ""
GESTCONF_EMAIL_PROVIDER_REQUIRED = False
# Alerte minimale aux opérateurs (D17, apps/core/alerts.py) : adresses séparées par des
# virgules ; vide = aucune alerte. Plafond d'alertes par heure, tous processus confondus.
GESTCONF_OPERATOR_EMAILS = [
    address.strip()
    for address in env.list("GESTCONF_OPERATOR_EMAILS", default=[])
    if address.strip()
]
if any("@" not in address for address in GESTCONF_OPERATOR_EMAILS):
    raise ImproperlyConfigured("GESTCONF_OPERATOR_EMAILS : adresses séparées par des virgules.")
GESTCONF_OPERATOR_ALERTS_PER_HOUR = env.int("GESTCONF_OPERATOR_ALERTS_PER_HOUR", default=10)

EMAIL_PROVIDERS = ("brevo", "mailjet", "smtp")
# Classes vérifiées dans anymail 15.2 (anymail/backends/brevo.py et mailjet.py).
ANYMAIL_BACKENDS = {
    "brevo": "anymail.backends.brevo.EmailBackend",
    "mailjet": "anymail.backends.mailjet.EmailBackend",
}


def email_settings_from_env(source: environ.Env, *, timeout: int) -> dict[str, Any]:
    """Réglages d'envoi de production, lus dans l'environnement (D10).

    - ``GESTCONF_EMAIL_PROVIDER`` vide : aucun fournisseur ; ``UnconfiguredEmailBackend``
      refuse tout envoi et l'application web refuse de démarrer (config/wsgi.py) ;
    - ``brevo`` : ``GESTCONF_BREVO_API_KEY`` ;
    - ``mailjet`` : ``GESTCONF_MAILJET_API_KEY`` et ``GESTCONF_MAILJET_SECRET_KEY`` ;
    - ``smtp`` (secours) : ``GESTCONF_SMTP_HOST`` (et ``_PORT``, ``_USER``, ``_PASSWORD``,
      ``_USE_SSL``).

    Un fournisseur déclaré exige aussi ``DEFAULT_FROM_EMAIL``. Incomplet ou inconnu :
    ``ImproperlyConfigured``, qui ne cite que des noms de variables, jamais une valeur.
    """
    provider = source.str("GESTCONF_EMAIL_PROVIDER", default="").strip().lower()
    if not provider:
        return {
            "GESTCONF_EMAIL_PROVIDER": "",
            "EMAIL_BACKEND": "apps.communications.backends.UnconfiguredEmailBackend",
        }
    if provider not in EMAIL_PROVIDERS:
        raise ImproperlyConfigured(
            f"GESTCONF_EMAIL_PROVIDER inconnu : choisir parmi {', '.join(EMAIL_PROVIDERS)}."
        )
    missing: list[str] = []

    def required(name: str) -> str:
        value = source.str(name, default="").strip()
        if not value:
            missing.append(name)
        return value

    from_email = required("DEFAULT_FROM_EMAIL")
    if from_email and "@" not in parseaddr(from_email)[1]:
        raise ImproperlyConfigured("DEFAULT_FROM_EMAIL n'est pas une adresse valide.")
    result: dict[str, Any] = {
        "GESTCONF_EMAIL_PROVIDER": provider,
        "DEFAULT_FROM_EMAIL": from_email,
        "SERVER_EMAIL": from_email,
    }
    if provider == "brevo":
        result["EMAIL_BACKEND"] = ANYMAIL_BACKENDS["brevo"]
        result["ANYMAIL"] = {
            "BREVO_API_KEY": required("GESTCONF_BREVO_API_KEY"),
            "REQUESTS_TIMEOUT": timeout,
        }
    elif provider == "mailjet":
        result["EMAIL_BACKEND"] = ANYMAIL_BACKENDS["mailjet"]
        result["ANYMAIL"] = {
            "MAILJET_API_KEY": required("GESTCONF_MAILJET_API_KEY"),
            "MAILJET_SECRET_KEY": required("GESTCONF_MAILJET_SECRET_KEY"),
            "REQUESTS_TIMEOUT": timeout,
        }
    else:
        use_ssl = source.bool("GESTCONF_SMTP_USE_SSL", default=False)
        user = source.str("GESTCONF_SMTP_USER", default="").strip()
        result.update(
            EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
            EMAIL_HOST=required("GESTCONF_SMTP_HOST"),
            EMAIL_PORT=source.int("GESTCONF_SMTP_PORT", default=465 if use_ssl else 587),
            EMAIL_HOST_USER=user,
            EMAIL_HOST_PASSWORD=required("GESTCONF_SMTP_PASSWORD") if user else "",
            EMAIL_USE_SSL=use_ssl,
            EMAIL_USE_TLS=not use_ssl,
            EMAIL_TIMEOUT=timeout,
        )
    if missing:
        raise ImproperlyConfigured(
            f"Fournisseur d'e-mails « {provider} » incomplet : renseigner {', '.join(missing)}."
        )
    return result


# --- API (Django REST Framework) -----------------------------------------------
REST_FRAMEWORK = {
    # Session Django, avec 401 sans session et 403 « csrf_failed » (plan L1 §4.6).
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.core.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    # Limites par portée seulement (plan L1 §4.7) : une vue n'est limitée que si elle
    # déclare throttle_scope. Pas de limite globale anon/user, qui coûterait des
    # écritures dans le cache en base à chaque requête de l'API.
    # Sous-classe de ScopedRateThrottle : compteurs dans le cache « throttle ».
    "DEFAULT_THROTTLE_CLASSES": ["apps.core.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "invitation": "10/min",  # consultation, acceptation, refus (par IP ou compte)
        "invitation_link": "3/hour",  # lien de liaison d'adresse (RG-20)
        "invitation_create": "20/hour",  # créations d'invitations, par compte
        "data_export": "3/hour",
        "account_deletion": "3/hour",
    },
    "NUM_PROXIES": GESTCONF_TRUSTED_PROXY_COUNT,
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GEST-CONF API",
    "DESCRIPTION": "API de la plateforme de gestion de conférences scientifiques.",
    # Version du projet, lue dans pyproject.toml (source unique, plan L1 §9.5).
    "VERSION": GESTCONF_VERSION,
    # Les chemins du schéma sont relatifs au point de montage /api.
    "SERVERS": [{"url": "/api"}],
    "SCHEMA_PATH_PREFIX": r"/v[0-9]+",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    # Un nom explicite par jeu de choix exposé (plan L1 §3.1, §9.5) : sans lui,
    # drf-spectacular peut renommer une énumération sans avertissement, ce qui
    # casse le client TypeScript. Une surcharge vise un jeu de choix, pas un champ.
    # Méta-test : tests/test_schema.py::test_every_schema_enum_has_explicit_name.
    "ENUM_NAME_OVERRIDES": {
        "HealthStatus": "apps.core.serializers.HealthStatus",
        "ServiceStatus": "apps.core.serializers.ServiceStatus",
        "JobsStatus": "apps.core.serializers.JobsStatus",
        "ErrorCode": "apps.core.errors.ErrorCode",
    },
    "POSTPROCESSING_HOOKS": [
        # Avant le crochet des énumérations, qui nomme ErrorCode (apps/core/schema.py).
        "apps.core.schema.add_api_error_component",
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
}

# --- Sécurité (valeurs communes ; durcies dans prod.py) ------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Angular lit le cookie CSRF pour renvoyer l'en-tête X-CSRFToken :
# il ne doit donc pas être HttpOnly (le cookie de session, lui, l'est).
CSRF_COOKIE_HTTPONLY = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# --- Journalisation -----------------------------------------------------------------
# Sortie d'erreur standard : Passenger la redirige vers son journal.
# Erreurs serveur (exception non rattrapée d'une requête) : alerte minimale aux opérateurs
# (D17, apps/core/alerts.py), sans corps, en-têtes, cookies ni paramètres. Le gestionnaire
# n'agit qu'au niveau ERROR et seulement si GESTCONF_OPERATOR_EMAILS est renseigné.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        "operator_alert": {"class": "apps.core.alerts.OperatorAlertHandler", "level": "ERROR"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Propagation vers « django » (console) conservée : l'alerte s'ajoute au journal.
        "django.request": {"handlers": ["operator_alert"], "propagate": True},
    },
}
