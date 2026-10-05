"""Acteur d'une opération métier (plan L1 §1.4, §7.2).

Les services ne reçoivent jamais l'objet ``request`` : la vue (ou la commande,
ou la tâche) construit une seule fois un ``Actor`` et le leur transmet. Il sert
au journal d'audit (L1.2) et aux contrôles de droits des services.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.http import client_ip

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.http import HttpRequest
    from rest_framework.request import Request

# Longueurs des colonnes correspondantes du futur AuditLog (plan L1 §3.5).
LABEL_MAX_LENGTH = 64
USER_AGENT_MAX_LENGTH = 255


class ActorKind(models.TextChoices):
    USER = "user", _("utilisateur")
    COMMAND = "command", _("commande")
    SYSTEM = "system", _("système")


@dataclass(frozen=True, slots=True, kw_only=True)
class Actor:
    """Qui agit, par quel canal, d'où.

    - ``USER`` : requête HTTP ; ``user`` vaut ``None`` pour un visiteur anonyme.
    - ``COMMAND`` : commande ``manage.py`` lancée par l'opérateur, ``label`` de la
      forme ``cli:<utilisateur système>``.
    - ``SYSTEM`` : tâche automatique (cron, file), ``label`` de la forme ``job:<type>``.

    ``label`` ne contient jamais l'adresse e-mail d'un utilisateur, qui
    survivrait à son anonymisation.
    """

    kind: ActorKind
    user: AbstractBaseUser | None = None
    label: str = ""
    ip: str | None = None
    user_agent: str = ""
    request_id: str = ""

    def __post_init__(self) -> None:
        if self.kind == ActorKind.USER:
            if self.label:
                raise ValueError("Un acteur utilisateur ne porte pas de libellé.")
        else:
            if self.user is not None:
                raise ValueError("Une commande ou une tâche n'agit pas au nom d'un utilisateur.")
            if not self.label or len(self.label) > LABEL_MAX_LENGTH:
                raise ValueError(
                    f"Libellé obligatoire, {LABEL_MAX_LENGTH} caractères au plus : {self.label!r}"
                )

    @classmethod
    def from_request(cls, request: HttpRequest | Request) -> Actor:
        user = getattr(request, "user", None)
        return cls(
            kind=ActorKind.USER,
            user=user if user is not None and user.is_authenticated else None,
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:USER_AGENT_MAX_LENGTH],
            request_id=getattr(request, "request_id", ""),
        )

    @classmethod
    def command(cls, label: str) -> Actor:
        return cls(kind=ActorKind.COMMAND, label=label)

    @classmethod
    def system(cls, label: str) -> Actor:
        return cls(kind=ActorKind.SYSTEM, label=label)
