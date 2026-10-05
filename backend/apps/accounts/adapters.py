"""Adaptateur d'allauth (plan L1 §4.2, « Adaptateurs »)."""

from __future__ import annotations

import secrets
from typing import Any

from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.mfa.adapter import DefaultMFAAdapter
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
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


# --- 2FA (plan L1 §4.2 « Adaptateurs », §4.10) ------------------------------------------


def mfa_cipher() -> MultiFernet:
    """Chiffrement des secrets 2FA : la première clé chiffre, toutes déchiffrent."""
    keys = [key.strip() for key in settings.GESTCONF_MFA_ENCRYPTION_KEYS if key.strip()]
    if not keys:
        raise ImproperlyConfigured("GESTCONF_MFA_ENCRYPTION_KEYS est vide.")
    return MultiFernet([Fernet(key.encode()) for key in keys])


class MFAAdapter(DefaultMFAAdapter):
    """Secret TOTP et graine des codes de secours chiffrés en base (allauth les stocke en
    clair par défaut) ; émetteur fixe (``MFA_TOTP_ISSUER``), jamais l'en-tête ``Host``."""

    def encrypt(self, text: str) -> str:
        return mfa_cipher().encrypt(text.encode()).decode()

    def decrypt(self, encrypted_text: str) -> str:
        try:
            return mfa_cipher().decrypt(encrypted_text.encode()).decode()
        except InvalidToken as exc:
            # Clé perdue ou retirée trop tôt : échec fermé (code refusé, pas de contournement).
            raise ImproperlyConfigured(
                "Secret 2FA indéchiffrable avec les clés actuelles."
            ) from exc
