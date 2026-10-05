"""Double authentification (plan L1 §4.2, §4.4, §4.10, §10.2 ; décisions D2, D3).

Les parcours (activation, connexion, réauthentification, codes de secours) sont ceux
d'``allauth.mfa`` en mode *headless*. Le projet y ajoute : le chiffrement des secrets
(``MFAAdapter``), l'état exposé par ``/v1/me``, le QR code d'enrôlement, la remise à zéro
par l'opérateur (``reset_mfa``) et la rotation des clés (``rotate_mfa_keys``).
"""

from __future__ import annotations

import base64
from typing import Any

from allauth.mfa.adapter import get_adapter as get_mfa_adapter
from allauth.mfa.models import Authenticator
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.adapters import mfa_cipher
from apps.accounts.models import User
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid

# Clé de session où allauth range le secret TOTP en attente d'activation (structure
# interne d'allauth 65.19.7, figée par un test de contrat, §4.5 et §10.2).
PENDING_TOTP_SECRET_SESSION_KEY = "mfa.totp.secret"  # noqa: S105 (nom de clé, pas un secret)

MFA_RESET_TEMPLATE = "mfa/email/mfa_reset"

# Champs chiffrés de ``Authenticator.data``, par type (allauth 65.19.7, lu dans le code).
ENCRYPTED_FIELDS: dict[str, tuple[str, ...]] = {
    Authenticator.Type.TOTP: ("secret",),
    Authenticator.Type.RECOVERY_CODES: ("seed",),
}


def register_mfa_templates() -> None:
    """Notifications de sécurité d'allauth.mfa, surchargées par le projet (FR/EN).

    Voie rapide : envoyées à la demande d'une personne authentifiée (§8.3).
    """
    from apps.communications.services import register_email_template

    for notification in ("totp_activated", "totp_deactivated", "recovery_codes_generated"):
        register_email_template(f"mfa/email/{notification}", fast_path=True)
    register_email_template(MFA_RESET_TEMPLATE)


def mfa_enabled(user: Any) -> bool:
    return get_mfa_adapter().is_mfa_enabled(user)


def pending_totp_secret(request: HttpRequest) -> str | None:
    secret = request.session.get(PENDING_TOTP_SECRET_SESSION_KEY)
    return secret if isinstance(secret, str) and secret else None


def totp_qr_data_url(request: HttpRequest) -> str | None:
    """QR code de l'enrôlement en ``data:image/svg+xml`` (CSP : ``img-src data:``).

    Le secret en attente est celui qu'allauth a placé dans la session lors du
    ``GET …/authenticators/totp`` : il ne transite jamais par une URL.
    """
    secret = pending_totp_secret(request)
    if secret is None:
        return None
    adapter = get_mfa_adapter()
    svg = adapter.build_totp_svg(adapter.build_totp_url(request.user, secret))
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


@transaction.atomic
def reset_mfa(user: User, *, actor: Actor, reason: str) -> int:
    """Supprime la 2FA d'un compte (perte de l'appareil, identité vérifiée hors bande).

    Les rôles de gestion exigeront un nouvel enrôlement (``MfaVerified``). Audit
    ``mfa.reset`` avec motif ; e-mail à l'adresse principale. Renvoie le nombre
    d'authentificateurs supprimés.
    """
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    authenticators = Authenticator.objects.select_for_update().filter(user=user)
    types = sorted(authenticators.values_list("type", flat=True))
    count = len(types)
    if count == 0:
        return 0
    authenticators.delete()
    record(
        "mfa.reset",
        actor=actor,
        obj=user,
        before={"types": types},
        after={"types": []},
        reason=reason,
    )
    from allauth.account.models import EmailAddress

    from apps.accounts.notifications import queue_account_email

    primary = EmailAddress.objects.get_primary_email(user) or user.email
    if primary:
        queue_account_email(MFA_RESET_TEMPLATE, primary, {"timestamp": timezone.now()}, user=user)
    return count


def rotate_mfa_keys(*, dry_run: bool = False) -> int:
    """Rechiffre tous les secrets 2FA avec la première clé (``MultiFernet.rotate``).

    À lancer après avoir placé la nouvelle clé en tête de ``GESTCONF_MFA_ENCRYPTION_KEYS``
    (l'ancienne restant dans la liste) ; l'ancienne clé peut ensuite être retirée.
    Idempotent. Renvoie le nombre d'authentificateurs rechiffrés.
    """
    cipher = mfa_cipher()
    rotated = 0
    for authenticator_id in Authenticator.objects.values_list("pk", flat=True).order_by("pk"):
        with transaction.atomic():
            authenticator = Authenticator.objects.select_for_update().get(pk=authenticator_id)
            fields = ENCRYPTED_FIELDS.get(authenticator.type, ())
            data = dict(authenticator.data)
            for field in fields:
                if isinstance(data.get(field), str):
                    data[field] = cipher.rotate(data[field].encode()).decode()
            migrated = data.get("migrated_codes")
            if isinstance(migrated, list):
                data["migrated_codes"] = [
                    cipher.rotate(code.encode()).decode() for code in migrated
                ]
            if data != authenticator.data:
                rotated += 1
                if not dry_run:
                    authenticator.data = data
                    authenticator.save(update_fields=["data"])
    return rotated
