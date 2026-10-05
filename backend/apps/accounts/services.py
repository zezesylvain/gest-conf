"""Services du compte : profil, préférences, consentements, désactivation (plan L1 §3.3, §4.8).

Les vues et les commandes construisent un ``Actor`` et appellent ces fonctions ;
chaque écriture est journalisée dans la même transaction (RG-17).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.consents import CURRENT_TEXT_VERSIONS
from apps.accounts.models import (
    Consent,
    ConsentKind,
    ConsentSource,
    Profile,
    User,
)
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid

PROFILE_FIELDS = (
    "title",
    "first_name",
    "last_name",
    "institution",
    "department",
    "country",
    "orcid",
    "bio",
)


def get_profile(user: User) -> Profile:
    """Profil du compte, non enregistré s'il n'existe pas encore (profil vide)."""
    try:
        return user.profile
    except Profile.DoesNotExist:
        return Profile(user=user)


def profile_complete(user: User) -> bool:
    return get_profile(user).is_complete


@transaction.atomic
def update_profile(user: User, data: Mapping[str, Any], *, actor: Actor) -> Profile:
    """Met à jour le profil (créé à la première écriture).

    Audit ``profile.updated`` : seule la **liste des champs modifiés** est
    journalisée, jamais leurs valeurs (données personnelles, plan §7.3).
    """
    unknown = set(data) - set(PROFILE_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    profile = get_profile(user)
    changed = sorted(name for name, value in data.items() if getattr(profile, name) != value)
    for name in changed:
        setattr(profile, name, data[name])
    try:
        profile.full_clean(exclude=["user"])
    except ValidationError as exc:
        raise Invalid(fields=exc.message_dict) from exc
    if changed or profile._state.adding:
        profile.save()
    if changed:
        record("profile.updated", actor=actor, obj=user, after={"fields": changed})
    return profile


@transaction.atomic
def set_locale(user: User, locale: str, *, actor: Actor) -> User:
    before = user.locale
    if locale != before:
        user.locale = locale
        user.full_clean(exclude=["password", "email"])
        user.save(update_fields=["locale", "updated_at"])
        record(
            "account.preferences_updated",
            actor=actor,
            obj=user,
            before={"locale": before},
            after={"locale": locale},
        )
    return user


# --- Consentements ---------------------------------------------------------------------


def current_consents(user: User) -> dict[str, Consent | None]:
    """Dernière ligne de chaque type de consentement (état courant), ``None`` sinon."""
    states: dict[str, Consent | None] = {kind: None for kind in ConsentKind.values}
    for consent in Consent.objects.filter(user=user).order_by("recorded_at", "id"):
        states[consent.kind] = consent
    return states


def privacy_notice_pending(user: User) -> bool:
    """Vrai si la version courante de la notice n'a pas été prise en compte (plan §4.3)."""
    latest = (
        Consent.objects.filter(user=user, kind=ConsentKind.PRIVACY_NOTICE, granted=True)
        .order_by("-recorded_at", "-id")
        .values_list("text_version", flat=True)
        .first()
    )
    return latest != CURRENT_TEXT_VERSIONS[ConsentKind.PRIVACY_NOTICE]


@transaction.atomic
def record_consent(user: User, kind: str, granted: bool, *, source: str, actor: Actor) -> Consent:
    """Ajoute une ligne de consentement (un retrait est une ligne ``granted=False``).

    La notice d'information ne se « retire » pas : c'est une prise de
    connaissance, pas un consentement (D15).
    """
    if kind not in ConsentKind.values:
        raise Invalid(fields={"kind": [_("Type de consentement inconnu.")]})
    if source not in ConsentSource.values:
        raise ValueError(f"Origine de consentement inconnue : {source}")
    if kind == ConsentKind.PRIVACY_NOTICE and not granted:
        raise Invalid(fields={"granted": [_("La prise de connaissance ne se retire pas.")]})
    consent = Consent.objects.create(
        user=user,
        kind=kind,
        granted=granted,
        text_version=CURRENT_TEXT_VERSIONS[kind],
        recorded_at=timezone.now(),
        source=source,
        ip=actor.ip,
    )
    record(
        "consent.granted" if granted else "consent.withdrawn",
        actor=actor,
        obj=user,
        after={"kind": kind, "text_version": consent.text_version, "source": source},
    )
    return consent


# --- Opérations de l'opérateur ----------------------------------------------------------


def delete_user_sessions(user: User) -> int:
    """Supprime les sessions ouvertes du compte (décodage des sessions non expirées)."""
    deleted = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()
            deleted += 1
    return deleted


@transaction.atomic
def deactivate_user(user: User, *, reason: str, actor: Actor) -> int:
    """Désactive un compte (plus de connexion possible) et ferme ses sessions."""
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    was_active = user.is_active
    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])
    closed = delete_user_sessions(user)
    record(
        "account.deactivated",
        actor=actor,
        obj=user,
        before={"is_active": was_active},
        after={"is_active": False, "sessions_closed": closed},
        reason=reason,
    )
    return closed
