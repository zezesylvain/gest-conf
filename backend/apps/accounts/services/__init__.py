"""Services de l'application ``accounts`` (logique métier, CLAUDE.md).

- ``account`` : profil, préférences, consentements, désactivation et réactivation ;
- ``personal_data`` : export et anonymisation (RG-18) ;
- ``mfa`` : double authentification ;
- ``access`` : droits d'un compte dans une édition (``edition_access``) ;
- ``roles`` : attribution et révocation des rôles (matrice §5.5) ;
- ``invitations`` : invitations aux rôles et RG-20.
"""

from apps.accounts.services.account import (
    PROFILE_FIELDS,
    current_consents,
    deactivate_user,
    delete_user_sessions,
    get_profile,
    privacy_notice_pending,
    profile_complete,
    reactivate_user,
    record_consent,
    set_locale,
    update_profile,
)

__all__ = [
    "PROFILE_FIELDS",
    "current_consents",
    "deactivate_user",
    "delete_user_sessions",
    "get_profile",
    "privacy_notice_pending",
    "profile_complete",
    "reactivate_user",
    "record_consent",
    "set_locale",
    "update_profile",
]
