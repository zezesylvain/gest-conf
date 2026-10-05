from typing import ClassVar

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from apps.core.models import TimeStampedModel


class User(AbstractBaseUser, TimeStampedModel):
    """Compte unique pour tous les rôles (étude §4 M2 et §8.2, table « user »).

    Volontairement minimal au lot L0 : le profil (nom, institution, ORCID...),
    les rôles par édition (UserRole), la vérification de l'e-mail et la 2FA
    sont traités au lot L1.

    Pas de PermissionsMixin : son champ is_superuser serait un rôle global
    implicite, contraire à la règle des rôles rattachés à une édition.
    """

    email = models.EmailField(_("adresse e-mail"), unique=True)
    is_active = models.BooleanField(_("actif"), default=True)
    locale = models.CharField(
        _("langue"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)
