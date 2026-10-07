"""Configuration de développement local."""

from .base import *

DEBUG = True

# « or » : une clé vide (copie brute de .env.example) retombe sur la clé de développement.
SECRET_KEY = (
    env.str("DJANGO_SECRET_KEY", default="") or "dev-only-insecure-key-do-not-use-in-production"
)

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# MariaDB recommandée (DATABASE_URL dans .env) ; SQLite en repli pour démarrer vite.
# Attention : SQLite ignore les verrous (select_for_update) et diffère de MariaDB
# sur plusieurs points ; la CI fait foi en exécutant les tests sur MariaDB.
DATABASES = {"default": database_from_env(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

# Le serveur de développement Angular (ng serve) relaie /api vers runserver.
CSRF_TRUSTED_ORIGINS = ["http://localhost:4200", "http://localhost:4201"]

# E-mails affichés dans la console de runserver (et de run_jobs), jamais envoyés.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
