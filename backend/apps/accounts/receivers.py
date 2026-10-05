"""Récepteurs de signaux : horodatage de connexion, audit, notification d'ajout d'adresse.

Branchés dans ``AccountsConfig.ready()`` (plan L1 §4.2, §7.2, §7.3). Signatures lues
dans le code d'allauth 65.19.7 et de Django 5.2.
"""

from __future__ import annotations

import time
from typing import Any

from allauth.account import signals as allauth_signals
from allauth.account.models import EmailAddress
from django.contrib.auth import signals as auth_signals
from django.dispatch import receiver
from django.http import HttpRequest

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.core.actor import Actor
from apps.core.audit import mask_email, record

EMAIL_ADDED_TEMPLATE = "account/email/email_added"


def _actor(request: HttpRequest | None) -> Actor:
    return Actor.from_request(request) if request is not None else Actor.system("auth")


@receiver(auth_signals.user_logged_in, dispatch_uid="gestconf_user_logged_in")
def on_user_logged_in(sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    """Après ``login()`` (clé de session déjà renouvelée) : début des 12 h absolues (D12)."""
    if request is None:
        return
    request.session[LOGIN_AT_SESSION_KEY] = time.time()
    record("auth.login", actor=_actor(request), obj=user)


@receiver(auth_signals.user_logged_out, dispatch_uid="gestconf_user_logged_out")
def on_user_logged_out(sender: Any, request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    # Expiration (D12) : déjà journalisée par le middleware sous « auth.session_expired ».
    if user is None or getattr(request, "gc_session_expired", False):
        return
    # request.user est encore le compte : logout() émet le signal avant de vider la session.
    record("auth.logout", actor=_actor(request), obj=user)


@receiver(allauth_signals.user_signed_up, dispatch_uid="gestconf_user_signed_up")
def on_user_signed_up(request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    record("account.signed_up", actor=_actor(request), obj=user, after={"locale": user.locale})


@receiver(allauth_signals.password_changed, dispatch_uid="gestconf_password_changed")
def on_password_changed(request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    record("auth.password_changed", actor=_actor(request), obj=user)


@receiver(allauth_signals.password_reset, dispatch_uid="gestconf_password_reset")
def on_password_reset(request: HttpRequest | None, user: Any, **kwargs: Any) -> None:
    record("auth.password_reset", actor=_actor(request), obj=user)


@receiver(allauth_signals.email_confirmed, dispatch_uid="gestconf_email_confirmed")
def on_email_confirmed(
    request: HttpRequest | None, email_address: EmailAddress, **kwargs: Any
) -> None:
    record(
        "account.email_confirmed",
        actor=_actor(request),
        obj=email_address.user,
        after={"email_masked": mask_email(email_address.email)},
    )


@receiver(allauth_signals.email_added, dispatch_uid="gestconf_email_added")
def on_email_added(
    request: HttpRequest | None, user: Any, email_address: EmailAddress, **kwargs: Any
) -> None:
    """Ajout d'une adresse : audit et notification à l'adresse principale (plan v3, §4.2).

    allauth ne notifie personne à l'ajout (vérifié) ; une session volée pourrait
    sinon ajouter une adresse à l'insu de la personne.
    """
    from apps.accounts.notifications import notify_email_added

    record(
        "account.email_added",
        actor=_actor(request),
        obj=user,
        after={"email_masked": mask_email(email_address.email)},
    )
    notify_email_added(user, email_address.email, actor=_actor(request))
