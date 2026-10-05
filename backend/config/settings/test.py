"""Configuration des tests (pytest).

Base SQLite en mémoire par défaut ; définir DATABASE_URL pour tester sur
MariaDB (c'est ce que fait la CI).
"""

from .base import *

DEBUG = False

SECRET_KEY = "test-only-secret-key"  # noqa: S105

ALLOWED_HOSTS = ["testserver"]

DATABASES = {"default": database_from_env(default="sqlite://:memory:")}

# Hachage rapide : les tests créent beaucoup d'utilisateurs.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
