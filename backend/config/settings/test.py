"""Configuration des tests (pytest).

Base SQLite en mémoire par défaut ; définir DATABASE_URL pour tester sur
MariaDB (c'est ce que fait la CI).
"""

from .base import *

DEBUG = False

SECRET_KEY = "test-only-secret-key"  # noqa: S105
# Clé Fernet de test (32 octets nuls encodés), jamais utilisée ailleurs.
GESTCONF_MFA_ENCRYPTION_KEYS = ["AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="]
# Clé Fernet de test du certificat de signature (32 octets 0x01), jamais utilisée ailleurs.
GESTCONF_SIGNING_ENCRYPTION_KEYS = ["AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="]

ALLOWED_HOSTS = ["testserver"]

DATABASES = {"default": database_from_env(default="sqlite://:memory:")}

# Hachage rapide : les tests créent beaucoup d'utilisateurs.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "GEST-CONF <no-reply@conference.test>"
GESTCONF_CRON_INTERVAL_SECONDS = 300
ADMINS = []

# Gabarits d'e-mails propres aux tests (tests/templates).
TEMPLATES[0]["DIRS"] = [BASE_DIR / "tests" / "templates"]
