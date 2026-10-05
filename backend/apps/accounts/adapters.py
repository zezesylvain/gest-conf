"""Adaptateur d'allauth (plan L1 §4.2, « Adaptateurs »)."""

from __future__ import annotations

import secrets
from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.http import HttpRequest
from django.utils import translation

from apps.accounts.notifications import queue_account_email
from apps.core.actor import Actor
from apps.core.audit import record


def request_locale() -> str:
    """Langue de la requête (``LocaleMiddleware``, ``Accept-Language``), ``fr`` ou ``en``."""
    language = (translation.get_language() or settings.LANGUAGE_CODE).split("-")[0].lower()
    available = {code for code, _name in settings.LANGUAGES}
    return language if language in available else settings.LANGUAGE_CODE


class AccountAdapter(DefaultAccountAdapter):
    def send_mail(self, template_prefix: str, email: str, context: dict) -> None:
        """Met l'e-mail en file (``communications``) au lieu de l'envoyer pendant la requête.

        Contexte réduit à une liste blanche de chaînes ; langue du compte destinataire,
        sinon celle de la requête. Les notifications de sécurité
        (``send_notification_mail``) passent aussi par ici.
        """
        queue_account_email(template_prefix, email, context, user=context.get("user"))

    def send_password_reset_mail(self, user: Any, email: str, context: dict[str, Any]) -> None:
        """Pas de lien de réinitialisation vers une adresse secondaire non vérifiée (plan v3).

        allauth l'enverrait : une adresse ajoutée par une session volée, jamais
        vérifiée, suffirait alors pour reprendre le compte. L'adresse du compte
        (adresse d'inscription), même non vérifiée, reste servie. La réponse de
        ``password/request`` est identique, et cet e-mail n'emprunte jamais la voie
        rapide : aucun écart de temps notable (§4.11).
        """
        is_account_address = email.lower() == (user.email or "").lower()
        verified = EmailAddress.objects.filter(user=user, email__iexact=email, verified=True)
        if not is_account_address and not verified.exists():
            return
        super().send_password_reset_mail(user, email, context)

    def send_account_already_exists_mail(self, email: str) -> None:
        """Inscription avec une adresse existante : même coût qu'une création de compte.

        Seule la création hache un mot de passe (≈ 750 ms contre ≈ 8 ms mesurés) :
        sans ce hachage factice, le temps de réponse révélerait l'existence du compte.
        """
        make_password(secrets.token_urlsafe(32))
        super().send_account_already_exists_mail(email)

    def save_user(self, request: HttpRequest, user: Any, form: Any, commit: bool = True) -> Any:
        """Langue du compte initialisée avec celle de la requête : l'e-mail de
        vérification part dans la langue du visiteur."""
        user = super().save_user(request, user, form, commit=False)
        user.locale = request_locale()
        if commit:
            user.save()
        return user

    def authentication_failed(self, request: HttpRequest, **credentials: Any) -> None:
        """Audit ``auth.login_failed`` : l'adresse saisie n'est jamais journalisée en clair.

        Compte connu : rattaché à l'entrée (objet) ; inconnu : seulement l'IP.
        """
        from apps.accounts.notifications import account_for_email

        email = credentials.get("email") or ""
        user = account_for_email(email) if email else None
        record("auth.login_failed", actor=Actor.from_request(request), obj=user)
