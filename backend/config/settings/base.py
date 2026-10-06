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
    "apps.conferences",
    "apps.portal",
    "apps.submissions",
    "apps.reviews",
    "apps.program",
    "apps.registrations",
    "apps.payments",
    "apps.events",
    # Après les applications du projet : leurs gabarits d'e-mails (account/email/*) priment.
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
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
    # Juste après l'authentification : 12 h absolues depuis la connexion (D12).
    "apps.accounts.middleware.AbsoluteSessionTimeoutMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Obligatoire pour allauth, en fin de liste.
    "allauth.account.middleware.AccountMiddleware",
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

AUTHENTICATION_BACKENDS = ["allauth.account.auth_backends.AuthenticationBackend"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- Comptes : django-allauth en mode headless (plan L1 §4.2, décisions D2, D4, D12) ---------
# URL publique du site (portail) : base des liens envoyés par e-mail. URL absolue, jamais
# déduite de l'en-tête Host, qui peut être forgé (§4.11).
GESTCONF_PUBLIC_URL = env.str("GESTCONF_PUBLIC_URL", default="http://localhost:4200").rstrip("/")

ACCOUNT_ADAPTER = "apps.accounts.adapters.AccountAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
# Confirmation du mot de passe faite dans Angular.
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
# Vérification obligatoire, en mode « lien » (option (a) de D6).
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_EMAIL_VERIFICATION_BY_CODE_ENABLED = False
ACCOUNT_PREVENT_ENUMERATION = True
# Rien n'est envoyé à une adresse inconnue : la plateforme ne peut pas servir à écrire
# à des adresses quelconques, et la réponse reste identique.
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False
# Alertes de sécurité (mot de passe changé, adresse supprimée...), faux par défaut.
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_LOGIN_BY_CODE_ENABLED = False
ACCOUNT_MAX_EMAIL_ADDRESSES = 3
ACCOUNT_CHANGE_EMAIL = False
# Réauthentification récente (5 min) pour ajouter ou supprimer une adresse, ou changer
# l'adresse principale : sinon une session volée suffit pour ajouter une adresse puis
# réinitialiser le mot de passe par elle (plan v3, §4.2 et §4.11).
ACCOUNT_REAUTHENTICATION_REQUIRED = True
# Objet des e-mails : préfixe porté par nos gabarits (« [GEST-CONF] … »).
ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
# Resserrement des limites d'allauth (§4.7) ; les autres valeurs par défaut sont gardées.
ACCOUNT_RATE_LIMITS = {
    "signup": "20/m/ip,100/3600s/ip",
    "reset_password": "20/m/ip,3/3600s/key",
}
# Lien de réinitialisation valable 2 h (Django : 3 jours par défaut).
PASSWORD_RESET_TIMEOUT = 2 * 3600

HEADLESS_ONLY = True
# Client « browser » seul : le client « app » utilise des jetons et des vues sans CSRF.
HEADLESS_CLIENTS = ("browser",)
HEADLESS_SERVE_SPECIFICATION = False
# Liens des e-mails vers le portail ; la clé dans le fragment (#) ne part ni dans les
# journaux du serveur ni dans l'en-tête Referer.
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{GESTCONF_PUBLIC_URL}/compte/verifier-email#{{key}}",
    "account_reset_password": f"{GESTCONF_PUBLIC_URL}/compte/mot-de-passe-oublie",
    "account_reset_password_from_key": f"{GESTCONF_PUBLIC_URL}/compte/reinitialiser#{{key}}",
    "account_signup": f"{GESTCONF_PUBLIC_URL}/compte/inscription",
}

# --- 2FA : allauth.mfa (décisions D2, D3 ; plan L1 §4.2, §4.4, §4.10) ---------------------
# TOTP et codes de secours seulement (ni WebAuthn ni « appareil de confiance »).
MFA_ADAPTER = "apps.accounts.adapters.MFAAdapter"
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]
MFA_TRUST_ENABLED = False
# Garde conservée : pas de 2FA avec une adresse non vérifiée (409 « unverified_email »).
MFA_ALLOW_UNVERIFIED_EMAIL = False
# Clés Fernet (base64 urlsafe, 32 octets) chiffrant le secret TOTP et la graine des codes
# de secours, séparées par des virgules : la première chiffre, toutes déchiffrent
# (MultiFernet). Obligatoire en production (prod.py) ; rotation : rotate_mfa_keys.
GESTCONF_MFA_ENCRYPTION_KEYS = env.list("GESTCONF_MFA_ENCRYPTION_KEYS", default=[])

# --- Sessions (D12) -------------------------------------------------------------------
# 12 h au plus, imposées par AbsoluteSessionTimeoutMiddleware (Django fait glisser
# l'échéance à chaque enregistrement de la session) ; cookie sans date d'expiration.
SESSION_COOKIE_AGE = 12 * 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
GESTCONF_SESSION_MAX_AGE = SESSION_COOKIE_AGE

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
# Même valeur pour allauth (limites de débit, IP des notifications de sécurité), §4.2.
ALLAUTH_TRUSTED_PROXY_COUNT = GESTCONF_TRUSTED_PROXY_COUNT

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
        "portal_upload": "60/hour",  # téléversements de fichiers publics, par compte
        # Soumissions (plan L3) : écritures (sauvegarde automatique comprise), dépôts de
        # fichier, soumissions et retraits, par compte.
        "submission_write": "600/hour",
        "submission_upload": "30/hour",
        "submission_submit": "20/hour",
        # Inscriptions (plan L6) : devis, par compte.
        "registration_quote": "300/hour",
        "registration_write": "60/hour",  # commandes
        "registration_upload": "30/hour",  # justificatifs
        "payment_check": "60/hour",  # interrogation au retour de la page de paiement
        "payment_webhook": "120/min",  # notifications des fournisseurs, par adresse IP
        # Jour J et attestations (plan L7) : images de signature, par compte.
        "signature_upload": "20/hour",
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
        "Locale": "apps.accounts.serializers.Locale",
        "ProfileTitle": "apps.accounts.models.ProfileTitle",
        "ConsentKind": "apps.accounts.models.ConsentKind",
        "ConsentSource": "apps.accounts.models.ConsentSource",
        "ConsentRequestSource": "apps.accounts.serializers.ConsentRequestSource",
        "Role": "apps.accounts.roles.Role",
        "Capability": "apps.accounts.roles.CAPABILITY_CHOICES",
        "Currency": "apps.core.money.Currency",
        # Plan L6 : inscriptions.
        "Period": "apps.registrations.models.Period",
        "Zone": "apps.registrations.models.Zone",
        "PaymentMethod": "apps.registrations.models.PaymentMethod",
        "DiscountKind": "apps.registrations.models.DiscountKind",
        "DiscountScope": "apps.registrations.models.DiscountScope",
        "LineKind": "apps.registrations.models.LineKind",
        "RegistrationStatus": "apps.registrations.models.RegistrationStatus",
        "OrderMethod": "apps.registrations.models.ORDER_METHOD_CHOICES",
        "ManualPaymentMethod": "apps.payments.models.MANUAL_METHOD_CHOICES",
        "DocumentKind": "apps.payments.models.DocumentKind",
        "PaymentStatus": "apps.payments.models.PaymentStatus",
        "PaymentProvider": "apps.payments.models.Provider",
        # Plan L7 : jour J.
        "CheckinOutcome": "apps.events.services.checkin.OUTCOME_CHOICES",
        "CheckinMethod": "apps.events.models.CheckinMethod",
        "RetiredTokenReason": "apps.registrations.models.RetiredTokenReason",
        "InvitableRole": "apps.accounts.roles.InvitableRole",
        "OcFunction": "apps.accounts.roles.OcFunction",
        "UserRoleStatus": "apps.accounts.models.UserRoleStatus",
        "RoleSource": "apps.accounts.models.RoleSource",
        "InvitationStatus": "apps.accounts.models.InvitationStatus",
        "SkippedReason": "apps.accounts.services.invitations.SkippedReason",
        "ActorKind": "apps.core.actor.ActorKind",
        "EditionStatus": "apps.conferences.models.EditionStatus",
        "FilePolicy": "apps.conferences.models.FilePolicy",
        "SubmissionLanguage": "apps.conferences.models.SUBMISSION_LANGUAGE_CHOICES",
        "SubmissionStatus": "apps.submissions.models.SubmissionStatus",
        "SubmissionFileKind": "apps.submissions.models.SubmissionFileKind",
        "SubmissionAction": "apps.submissions.serializers.SUBMISSION_ACTION_CHOICES",
        # Plan L5 : programme.
        "SessionKind": "apps.program.models.SessionKind",
        "SessionRoleKind": "apps.program.models.SessionRoleKind",
        "Equipment": "apps.program.models.Equipment",
        "ProgramConflictKind": "apps.program.serializers.PROGRAM_CONFLICT_CHOICES",
        "PassageRole": "apps.program.serializers.PASSAGE_ROLE_CHOICES",
        "SectionType": "apps.portal.models.SectionType",
        "MenuLocation": "apps.portal.models.MenuLocation",
        "PublicFileKind": "apps.core.models.PublicFileKind",
        "PortalFileKind": "apps.portal.serializers.PORTAL_FILE_KIND_CHOICES",
        "NotificationKind": "apps.communications.models.NotificationKind",
        "AssignmentStatus": "apps.reviews.models.AssignmentStatus",
        "ConflictKind": "apps.reviews.models.ConflictKind",
        "ConflictSource": "apps.reviews.models.ConflictSource",
        "ReviewStatus": "apps.reviews.models.ReviewStatus",
        "Recommendation": "apps.reviews.models.Recommendation",
        "DecisionOutcome": "apps.reviews.models.DecisionOutcome",
        "ScreeningDecision": "apps.reviews.serializers.SCREENING_DECISION_CHOICES",
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
# Émetteur affiché par l'application TOTP : nom fixe, jamais l'en-tête Host (allauth
# l'utiliserait par défaut, MFA_TOTP_ISSUER vide).
MFA_TOTP_ISSUER = GESTCONF_SITE_NAME
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
# Fichiers déposés (règle n° 8) : HORS de la racine web ; servis par l'API seulement.
# Fichiers publics (E4, lot L2) dans le sous-dossier « public ».
GESTCONF_FILES_DIR = Path(env.str("GESTCONF_FILES_DIR", default=str(BASE_DIR / "var" / "files")))
# Fichiers des auteurs (lot L3, F2) : privés, servis par un endpoint authentifié (règle
# n° 8 sans adaptation). Par défaut sous GESTCONF_FILES_DIR (une seule sauvegarde).
GESTCONF_PRIVATE_FILES_DIR = Path(
    env.str("GESTCONF_PRIVATE_FILES_DIR", default=str(GESTCONF_FILES_DIR / "private"))
)
# Durées de conservation de D15 : simulation seule tant qu'elles ne sont pas validées
# par le commanditaire (les purges imposées par la sécurité s'appliquent toujours).
GESTCONF_RETENTION_ENFORCED = env.bool("GESTCONF_RETENTION_ENFORCED", default=False)

# --- Paiement en ligne (plan L6, J6 ; bilan de L6.0) ----------------------------------------
# Fournisseur : vide (paiement manuel seul), « fake » (démonstration et tests, refusé en
# production sauf recette déclarée) ou « cinetpay » (API v1). Secrets dans l'environnement
# seulement (règle n° 11), jamais dans le dépôt.
GESTCONF_PAYMENT_PROVIDER = env.str("GESTCONF_PAYMENT_PROVIDER", default="")
GESTCONF_ALLOW_FAKE_PAYMENTS = env.bool("GESTCONF_ALLOW_FAKE_PAYMENTS", default=False)
CINETPAY_API_KEY = env.str("CINETPAY_API_KEY", default="")
CINETPAY_API_PASSWORD = env.str("CINETPAY_API_PASSWORD", default="")
CINETPAY_SANDBOX = env.bool("CINETPAY_SANDBOX", default=True)
CINETPAY_TIMEOUT_SECONDS = env.float("CINETPAY_TIMEOUT_SECONDS", default=8.0)

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
        # Sous-ensemble de police à chaque PDF (fpdf2, plan L6) : une dizaine de lignes INFO
        # par facture, sans intérêt pour l'exploitation.
        "fontTools": {"level": "WARNING"},
    },
}
