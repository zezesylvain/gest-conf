"""Configuration commune à tous les environnements.

Toute valeur sensible ou propre à un environnement (secret, base de données,
hôtes autorisés) est lue dans les variables d'environnement ou dans un fichier
.env situé hors du dépôt (voir .env.example). Ne jamais committer de secret.
"""

from pathlib import Path

import environ
import pymysql

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
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
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

# Seuls les gabarits des bibliothèques (page Swagger en développement) sont utilisés.
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


def database_from_env(default: str | None = None) -> dict:
    """Construit la configuration de la base à partir de DATABASE_URL.

    Exemple : mysql://gestconf:motdepasse@localhost:3306/gestconf
    """
    config = env.db("DATABASE_URL") if default is None else env.db("DATABASE_URL", default=default)
    if config["ENGINE"] == "django.db.backends.mysql":
        config.setdefault("OPTIONS", {}).update({"charset": "utf8mb4"})
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
# Toutes les dates sont stockées en UTC ; la conversion dans le fuseau de
# l'édition se fait côté interface.
TIME_ZONE = "UTC"
USE_TZ = True

# --- API (Django REST Framework) -----------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "300/min", "auth": "10/min"},
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "GEST-CONF API",
    "DESCRIPTION": "API de la plateforme de gestion de conférences scientifiques.",
    "VERSION": "1.0.0",
    # Les chemins du schéma sont relatifs au point de montage /api.
    "SERVERS": [{"url": "/api"}],
    "SCHEMA_PATH_PREFIX": r"/v[0-9]+",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
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
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
