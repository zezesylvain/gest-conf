"""Photo du profil (E12, plan L2 §2.5) : fichier public de nature « photo », réencodé
(800 px, sans EXIF), servi sur le portail seulement si le compte est actif et a donné le
consentement ``photo_publication``.

Audit ``profile.photo_changed`` : jamais le nom d'origine ni le contenu (donnée personnelle).
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import ConsentKind, Profile, User
from apps.accounts.services.account import current_consents, get_profile
from apps.core import public_files
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.models import PublicFile, PublicFileKind


@transaction.atomic
def set_photo(user: User, *, data: bytes, name: str, actor: Actor) -> Profile:
    """Remplace la photo (l'ancienne est supprimée après validation de la transaction)."""
    profile = get_profile(user)
    if profile._state.adding:
        profile.save()
    profile = Profile.objects.select_for_update().get(pk=profile.pk)
    previous = profile.photo
    profile.photo = public_files.store(
        data=data, name=name, kind=PublicFileKind.PHOTO, published=True
    )
    profile.save(update_fields=["photo"])
    if previous is not None:
        public_files.delete(previous)
    record("profile.photo_changed", actor=actor, obj=user, after={"photo": True})
    return profile


@transaction.atomic
def remove_photo(user: User, *, actor: Actor) -> Profile:
    profile = get_profile(user)
    if profile._state.adding or profile.photo_id is None:
        return profile
    profile = Profile.objects.select_for_update().get(pk=profile.pk)
    previous = profile.photo
    profile.photo = None
    profile.save(update_fields=["photo"])
    public_files.delete(previous)
    record("profile.photo_changed", actor=actor, obj=user, after={"photo": False})
    return profile


def photo_is_public(public_file: PublicFile) -> bool:
    """Photo servie seulement pour un compte actif qui a consenti à sa publication."""
    profile = Profile.objects.select_related("user").filter(photo=public_file).first()
    if profile is None or not profile.user.is_active:
        return False
    consent = current_consents(profile.user).get(ConsentKind.PHOTO_PUBLICATION)
    return bool(consent and consent.granted)
