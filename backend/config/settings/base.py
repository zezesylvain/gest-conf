"""Configuration commune à tous les environnements.

Toute valeur sensible ou propre à un environnement (secret, base de données,
hôtes autorisés) est lue dans les variables d'environnement ou dans un fichier
.env situé hors du dépôt (voir .env.example). Ne jamais committer de secret.
"""

import tomllib
from pathlib import Path

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
    # Plafond des envois immédiats d'e-mails par requête (voie rapide, plan L1 §8.3).
    "apps.communications.middleware.EmailFastPathMiddleware",
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

# Gabarits des applications : e-mails (apps/*/templates) et page Swagger en développement.
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

# --- E-mails (plan L1 §8.3, décision D10) ------------------------------------------------
# Nom affiché dans les gabarits (objet et corps) ; fixe, jamais saisi par un utilisateur.
GESTCONF_SITE_NAME = env.str("GESTCONF_SITE_NAME", default="GEST-CONF")
# Backend : console en développement, locmem en test (test.py), fournisseur par API en
# production via django-anymail, par exemple « anymail.backends.brevo.EmailBackend » ou
# « anymail.backends.mailjet.EmailBackend » (classes vérifiées dans anymail 15.2).
EMAIL_BACKEND = env.str(
    "GESTCONF_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="GEST-CONF <no-reply@localhost>")
SERVER_EMAIL = env.str("SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# Clés du fournisseur : seules celles définies sont transmises à anymail, qui refuse de
# démarrer si la clé du backend choisi manque. Délai réseau borné (connexion, lecture) :
# la voie rapide envoie pendant la requête HTTP, au plus 3 fois (plan L1 §8.3).
ANYMAIL = {
    name: value
    for name, value in {
        "BREVO_API_KEY": env.str("BREVO_API_KEY", default=""),
        "MAILJET_API_KEY": env.str("MAILJET_API_KEY", default=""),
        "MAILJET_SECRET_KEY": env.str("MAILJET_SECRET_KEY", default=""),
    }.items()
    if value
}
ANYMAIL["REQUESTS_TIMEOUT"] = (
    env.float("GESTCONF_EMAIL_CONNECT_TIMEOUT", default=3.05),
    env.float("GESTCONF_EMAIL_READ_TIMEOUT", default=10.0),
)
# Plafond global d'envoi par heure (plan L1 §8.3, D16) : au-delà, les e-mails restent en
# file. À aligner sur le quota du fournisseur retenu (D10, à vérifier).
GESTCONF_EMAIL_MAX_PER_HOUR = env.int("GESTCONF_EMAIL_MAX_PER_HOUR", default=200)

# --- Opérateurs et alertes (décision D17) ---------------------------------------------
# Adresses des opérateurs, séparées par des virgules. Alertes minimales seulement
# (apps.core.alerts) : jamais le détail d'une requête.
ADMINS = [(address, address) for address in env.list("GESTCONF_OPERATORS", default=[])]
EMAIL_SUBJECT_PREFIX = "[GEST-CONF] "
GESTCONF_OPERATOR_ALERTS_PER_HOUR = env.int("GESTCONF_OPERATOR_ALERTS_PER_HOUR", default=10)

# --- Tâches planifiées (règle n° 9, plan L1 §8.2 et §8.4) -----------------------------
# Intervalle du cron de run_jobs, en secondes (décision d'hébergement H-6, contrôle M01) :
# /health signale « late » après trois intervalles sans passage réussi.
GESTCONF_CRON_INTERVAL_SECONDS = env.int("GESTCONF_CRON_INTERVAL_SECONDS", default=300)
# Verrou des commandes cron (décision H-5) : « flock » (fichier dans GESTCONF_LOCK_DIR)
# ou « database » (GET_LOCK de MariaDB).
GESTCONF_COMMAND_LOCK = env.str("GESTCONF_COMMAND_LOCK", default="flock")
GESTCONF_LOCK_DIR = Path(env.str("GESTCONF_LOCK_DIR", default=str(BASE_DIR / "tmp")))
# Durées de conservation de D15 : simulation seule tant qu'elles ne sont pas validées
# par le commanditaire (les purges imposées par la sécurité s'appliquent toujours).
GESTCONF_RETENTION_ENFORCED = env.bool("GESTCONF_RETENTION_ENFORCED", default=False)

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
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
        # Erreurs 5xx : alerte minimale aux opérateurs (D17), sans détail de la requête.
        "operators": {"()": "apps.core.alerts.OperatorAlertHandler"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {
            "handlers": ["console", "operators"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
