"""Cycle de vie des inscriptions (plan L6, J5) : **seul** module qui écrit le statut d'une
inscription (règle n° 4 transposée, méta-test).

``transition(registration, to_status, actor=…, reason=…)`` vérifie la légalité, verrouille
la ligne, applique les effets du statut (clé active, jeton QR, quotas et codes promo),
écrit l'historique et le journal, puis met les e-mails en file (envoyés après validation).

| De | Vers | Effets |
|---|---|---|
| en attente | confirmée | jeton QR, utilisation du code promo consommée |
| en attente | annulée, expirée | places et utilisation du code rendues |
| confirmée | annulée | places rendues, jeton QR retiré (empreinte gardée), remboursement dû (J9) |
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import ErrorCode, RuleViolation
from apps.registrations.models import (
    Registration,
    RegistrationStatus,
    RegistrationStatusHistory,
    RetiredQrToken,
    RetiredTokenReason,
)
from apps.registrations.models import RegistrationStatus as S
from apps.registrations.tokens import new_token, token_hash

TRANSITIONS: frozenset[tuple[str, str]] = frozenset(
    {
        (S.PENDING, S.CONFIRMED),
        (S.PENDING, S.CANCELLED),
        (S.PENDING, S.EXPIRED),
        (S.CONFIRMED, S.CANCELLED),
    }
)


def can_transition(from_status: str, to_status: str) -> bool:
    return (from_status, to_status) in TRANSITIONS


def record_creation(registration: Registration, *, actor: Actor) -> None:
    """Première ligne d'historique (« → en attente »), écrite par la commande."""
    RegistrationStatusHistory.objects.create(
        registration=registration,
        from_status="",
        to_status=registration.status,
        at=timezone.now(),
        actor=actor.user,
        actor_label="" if actor.user else actor.label,
    )


@transaction.atomic
def transition(
    registration: Registration,
    to_status: str,
    *,
    actor: Actor,
    reason: str = "",
    refund_due: Decimal | None = None,
) -> Registration:
    from apps.registrations import notifications
    from apps.registrations.services import pricing

    registration = (
        Registration.objects.select_for_update()
        .select_related("edition", "user", "promo_code")
        .get(pk=registration.pk)
    )
    from_status = registration.status
    if not can_transition(from_status, to_status):
        raise RuleViolation(
            _("Changement de statut impossible depuis « %(status)s ».")
            % {"status": RegistrationStatus(from_status).label},
            code=ErrorCode.INVALID_TRANSITION,
        )
    now = timezone.now()
    options = list(registration.options.all())
    fields = ["status", "updated_at"]
    registration.status = to_status
    if to_status == S.CONFIRMED:
        registration.qr_token = new_token()
        registration.confirmed_at = now
        registration.due_at = None
        fields += ["qr_token", "confirmed_at", "due_at"]
        if registration.promo_code is not None:
            pricing.consume_promo(registration.promo_code)
    else:
        if registration.qr_token:
            # Badge annulé (plan L7, K4) : l'accueil le reconnaît à son empreinte.
            RetiredQrToken.objects.create(
                registration=registration,
                token_hash=token_hash(registration.qr_token),
                reason=RetiredTokenReason.CANCELLED,
                retired_at=now,
            )
        registration.active_key = None
        registration.qr_token = None
        registration.closed_at = now
        fields += ["active_key", "qr_token", "closed_at"]
        pricing.release_options(options)
        if from_status == S.PENDING and registration.promo_code is not None:
            pricing.release_promo(registration.promo_code)
        if refund_due is not None:
            registration.refund_due = refund_due
            fields.append("refund_due")
    registration.save(update_fields=fields)
    RegistrationStatusHistory.objects.create(
        registration=registration,
        from_status=from_status,
        to_status=to_status,
        at=now,
        actor=actor.user,
        actor_label="" if actor.user else actor.label,
        reason=reason,
    )
    record(
        f"registration.{to_status}",
        actor=actor,
        edition=registration.edition,
        obj=registration,
        before={"status": from_status},
        after={"status": to_status},
        reason=reason,
    )
    notifications.status_changed(registration, from_status)
    return registration
