"""Configuration de développement local."""

from .base import *

DEBUG = True

# « or » : une clé vide (copie brute de .env.example) retombe sur la clé de développement.
SECRET_KEY = (
    env.str("DJANGO_SECRET_KEY", default="") or "dev-only-insecure-key-do-not-use-in-production"
)

# Clé de chiffrement 2FA dérivée de SECRET_KEY si aucune n'est fournie (développement seul).
if not GESTCONF_MFA_ENCRYPTION_KEYS:
    import base64
    import hashlib

    GESTCONF_MFA_ENCRYPTION_KEYS = [
        base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
    ]

# Idem pour le certificat de signature PAdES (plan L7, K19), clé distincte.
if not GESTCONF_SIGNING_ENCRYPTION_KEYS:
    import base64
    import hashlib

    GESTCONF_SIGNING_ENCRYPTION_KEYS = [
        base64.urlsafe_b64encode(
            hashlib.sha256(b"signing:" + SECRET_KEY.encode()).digest()
        ).decode()
    ]

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# MariaDB recommandée (DATABASE_URL dans .env) ; SQLite en repli pour démarrer vite.
# Attention : SQLite ignore les verrous (select_for_update) et diffère de MariaDB
# sur plusieurs points ; la CI fait foi en exécutant les tests sur MariaDB.
DATABASES = {"default": database_from_env(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}

# Le serveur de développement Angular (ng serve) relaie /api vers runserver.
CSRF_TRUSTED_ORIGINS = ["http://localhost:4200", "http://localhost:4201"]

# Paiement en ligne de démonstration (plan L6, J6) : fournisseur factice par défaut.
GESTCONF_PAYMENT_PROVIDER = env.str("GESTCONF_PAYMENT_PROVIDER", default="fake")
