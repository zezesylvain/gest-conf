"""E-mails du compte : gabarits déclarés et contexte en liste blanche (plan L1 §4.2, §8.3).

allauth passe à ses gabarits des objets de l'ORM et la requête (``user``,
``request``, ``current_site``, ``uid``, ``key``). Les gabarits du projet ne
reçoivent que les chaînes de ``ALLOWED_CONTEXT_KEYS`` : un futur éditeur de
modèles (L3) ne pourra pas afficher ``{{ user.password }}``.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from allauth.account.models import EmailAddress
from django.utils import formats, timezone, translation

from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.core.actor import Actor

# Variables transmises aux gabarits (toutes converties en chaînes) ; le reste est écarté.
ALLOWED_CONTEXT_KEYS = frozenset(
    {
        "activate_url",
        "password_reset_url",
        "signup_url",
        "ip",
        "user_agent",
        "timestamp",
        # Notifications d'adresses : adresses concernées, dans le corps seulement.
        "from_email",
        "to_email",
        "deleted_email",
        "added_email",
    }
)

EMAIL_ADDED_TEMPLATE = "account/email/email_added"


def register_account_templates() -> None:
    """Gabarits d'allauth surchargés par le projet (``templates/account/email``).

    Sensibles (lien à jeton, corps purgé à l'envoi) : vérification et
    réinitialisation. Voie rapide : e-mails envoyés quelle que soit l'existence
    d'un compte, ou à la demande d'une personne déjà authentifiée ; **jamais** la
    réinitialisation (oracle temporel, §8.3).
    """
    register_email_template(
        "account/email/email_confirmation_signup", sensitive=True, fast_path=True
    )
    register_email_template("account/email/email_confirmation", sensitive=True, fast_path=True)
    register_email_template("account/email/account_already_exists", fast_path=True)
    register_email_template("account/email/password_reset_key", sensitive=True)
    for notification in (
        "password_reset",
        "password_changed",
        "password_set",
        "email_changed",
        "email_deleted",
        "email_added",
    ):
        register_email_template(f"account/email/{notification}", fast_path=True)


def format_timestamp(value: datetime, locale: str) -> str:
    with translation.override(locale):
        local = timezone.localtime(value, UTC)
        return f"{formats.date_format(local, 'DATETIME_FORMAT')} UTC"


def safe_context(context: Mapping[str, Any], locale: str) -> dict[str, str]:
    """Réduit le contexte d'allauth à des chaînes en liste blanche."""
    result: dict[str, str] = {}
    for key in ALLOWED_CONTEXT_KEYS & set(context):
        value = context[key]
        if value is None:
            continue
        if isinstance(value, datetime):
            result[key] = format_timestamp(value, locale)
        else:
            result[key] = str(value)
    return result


def account_for_email(email: str) -> Any:
    """Compte auquel appartient l'adresse (vérifiée ou non), ``None`` sinon."""
    from apps.accounts.models import User

    address = EmailAddress.objects.filter(email__iexact=email).select_related("user").first()
    if address is not None:
        return address.user
    return User.objects.filter(email__iexact=email).first()


def queue_account_email(
    template_prefix: str, email: str, context: Mapping[str, Any], *, user: Any = None
) -> None:
    """Rend dans la langue du destinataire et met en file (au lieu d'un envoi synchrone)."""
    to_user = user if user is not None else account_for_email(email)
    locale = resolve_locale(None, to_user)
    queue_email(
        template_code=template_prefix,
        to_email=email,
        to_user=to_user,
        locale=locale,
        context=safe_context(context, locale),
    )


def notify_email_added(user: Any, added_email: str, *, actor: Actor) -> None:
    """« Une adresse a été ajoutée à votre compte », vers l'adresse principale si elle diffère."""
    primary = EmailAddress.objects.get_primary_email(user)
    if not primary or primary.lower() == added_email.lower():
        return
    queue_account_email(
        EMAIL_ADDED_TEMPLATE,
        primary,
        {
            "added_email": added_email,
            "ip": actor.ip or "",
            "user_agent": actor.user_agent,
            "timestamp": timezone.now(),
        },
        user=user,
    )
