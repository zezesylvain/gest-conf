from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Gestionnaire d'utilisateurs identifiés par leur adresse e-mail."""

    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email: str | None) -> str:
        # Adresse entière en minuscules : MariaDB (collation *_ci) compare déjà
        # sans tenir compte de la casse, SQLite non. On aligne les deux.
        return (email or "").strip().lower()

    def create_user(self, email: str, password: str | None = None, **extra_fields: Any):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
