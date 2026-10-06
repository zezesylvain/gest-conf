"""Commande, annulation, gratuité et justificatif d'une inscription (plan L6, J2 à J5, J7, J9).

Le statut ne change que par ``apps.registrations.workflow.transition`` ; ce module prépare
les inscriptions (prix figé, réservations, échéance) et décide des remboursements dus.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Profile, User
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.money import quantize
from apps.core.private_files import PrivateStore, sniff
from apps.registrations import notifications, workflow
from apps.registrations.models import (
    ACTIVE_STATUSES,
    LineKind,
    PaymentMethod,
    Registration,
    RegistrationSettings,
    RegistrationStatus,
    RetiredQrToken,
    RetiredTokenReason,
)
from apps.registrations.services import pricing
from apps.registrations.services.settings import offered_methods, registration_settings
from apps.registrations.tokens import new_token, token_hash

PROOFS = PrivateStore("registration-proofs")

# Effets d'une commande déclarés par les autres applications (pro forma de ``payments``) :
# ``registrations`` ne dépend pas de ``payments``.
type OrderEffect = Callable[[Registration, Actor], None]
_ORDER_EFFECTS: list[OrderEffect] = []


def register_order_effect(effect: OrderEffect) -> None:
    if effect not in _ORDER_EFFECTS:
        _ORDER_EFFECTS.append(effect)


# Avant d'expirer une commande, les autres applications peuvent demander un report (paiement
# en ligne en cours, fournisseur injoignable) : f(inscription) -> True pour reporter.
type ExpiryCheck = Callable[[Registration], bool]
_EXPIRY_CHECKS: list[ExpiryCheck] = []


def register_expiry_check(check: ExpiryCheck) -> None:
    if check not in _EXPIRY_CHECKS:
        _EXPIRY_CHECKS.append(check)


PROOF_MAX_BYTES = 5 * 1024 * 1024
BILLING_FIELDS = ("billing_name", "billing_organization", "billing_address")
PAID_METHODS = (PaymentMethod.ONLINE, PaymentMethod.TRANSFER, PaymentMethod.ONSITE)


# --- Échéances (J5) ---------------------------------------------------------------------------


def _local_midnight(day: dt.date, tz_name: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(0), tzinfo=ZoneInfo(tz_name)).astimezone(dt.UTC)


def due_at_for(
    edition: Edition, settings: RegistrationSettings, method: str, now: dt.datetime
) -> dt.datetime | None:
    """Échéance de paiement : 72 h en ligne, 30 jours par virement, **sans dépasser la veille
    de la conférence** (J5) ; sur place : fin de la conférence. Aucune pour une gratuité."""
    starts = _local_midnight(edition.start_date, edition.timezone) if edition.start_date else None
    if method == PaymentMethod.ONLINE:
        due = now + dt.timedelta(hours=settings.online_deadline_hours)
    elif method == PaymentMethod.TRANSFER:
        due = now + dt.timedelta(days=settings.transfer_deadline_days)
    elif method == PaymentMethod.ONSITE:
        if edition.end_date is None:
            return None
        return _local_midnight(edition.end_date + dt.timedelta(days=1), edition.timezone)
    else:
        return None
    if starts is not None:
        due = min(due, starts)
        if due <= now:
            raise Invalid(
                fields={"method": [_("Moyen de paiement impossible si près de la conférence.")]}
            )
    return due


# --- Commande (J2 à J5) ---------------------------------------------------------------------------


def profile_country(user: User) -> str:
    country = Profile.objects.filter(user=user).values_list("country", flat=True).first()
    if not country:
        raise RuleViolation(
            _("Indiquez votre pays dans votre profil : il détermine le tarif."),
            code=ErrorCode.PROFILE_INCOMPLETE,
            fields={"country": [_("Pays obligatoire.")]},
        )
    return country


def default_billing(user: User) -> dict[str, str]:
    profile = Profile.objects.filter(user=user).first()
    if profile is None:
        return {"billing_name": "", "billing_organization": ""}
    return {
        "billing_name": f"{profile.first_name} {profile.last_name}".strip(),
        "billing_organization": profile.institution,
    }


def _already_registered() -> RuleViolation:
    return RuleViolation(
        _("Vous avez déjà une inscription à cette édition."), code=ErrorCode.ALREADY_REGISTERED
    )


@transaction.atomic
def place_order(
    edition: Edition,
    user: User,
    *,
    category: str,
    options: list[str] | tuple[str, ...] = (),
    promo_code: str = "",
    method: str,
    billing: Mapping[str, str] | None = None,
    actor: Actor,
    by_committee: bool = False,
) -> Registration:
    """Commande d'une inscription : prix figé, places et code promo réservés, échéance.

    - participant : inscriptions ouvertes en ligne, moyens proposés par l'édition ;
    - CO (``by_committee``) : aussi après la clôture (tarif « sur place », J2), tout moyen ;
    - montant nul : confirmée aussitôt (moyen « aucun paiement »).
    """
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    ensure_editable(edition)
    country = profile_country(user)
    now = timezone.now()
    if not by_committee and not pricing.is_open_online(edition, now):
        raise RuleViolation(
            _("Les inscriptions en ligne sont fermées."), code=ErrorCode.REGISTRATION_CLOSED
        )
    if Registration.objects.filter(edition=edition, user=user, status__in=ACTIVE_STATUSES).exists():
        raise _already_registered()
    settings = registration_settings(edition)
    # Après la clôture, la période est « sur place » (commande du CO) ; avant l'ouverture,
    # ``quote`` refuse (409 registration_closed).
    quote = pricing.quote(
        edition,
        category=category,
        options=list(options),
        promo_code=promo_code,
        country=country,
        at=now,
    )
    if quote.total == 0:
        method = PaymentMethod.FREE
    else:
        allowed = PAID_METHODS if by_committee else offered_methods(settings)
        if method not in allowed:
            raise Invalid(fields={"method": [_("Moyen de paiement non proposé.")]})
    due_at = due_at_for(edition, settings, method, now)
    pricing.reserve_options(quote.options)
    if quote.promo_code is not None:
        pricing.reserve_promo(quote.promo_code)
    values = {**default_billing(user), **{k: v for k, v in (billing or {}).items() if v}}
    registration = Registration(
        edition=edition,
        user=user,
        category=quote.category,
        status=RegistrationStatus.PENDING,
        period=quote.period,
        zone=quote.zone,
        method=method,
        lines=[line.as_json() for line in quote.lines],
        total=quote.total,
        currency=quote.currency,
        promo_code=quote.promo_code,
        due_at=due_at,
        active_key=Registration.make_active_key(edition.pk, user.pk),
        **{name: values.get(name, "") for name in BILLING_FIELDS},
    )
    try:
        with transaction.atomic():
            registration.save()
    except IntegrityError as exc:  # commande simultanée de la même personne
        raise _already_registered() from exc
    registration.options.set(quote.options)
    workflow.record_creation(registration, actor=actor)
    record(
        "registration.ordered",
        actor=actor,
        edition=edition,
        obj=registration,
        after=snapshot(registration),
    )
    if quote.total == 0:
        return workflow.transition(registration, RegistrationStatus.CONFIRMED, actor=actor)
    notifications.ordered(registration)
    for effect in _ORDER_EFFECTS:
        effect(registration, actor)
    return registration


# --- Annulation et remboursement dû (J9) ----------------------------------------------------------


def paid_amount(registration: Registration) -> Decimal:
    from apps.payments.models import PaymentStatus

    total = registration.payments.filter(status=PaymentStatus.SUCCEEDED).aggregate(
        total=Sum("amount")
    )["total"]
    return total or Decimal(0)


def refund_percent(settings: RegistrationSettings, now: dt.datetime) -> int:
    """Part remboursée selon la date limite d'annulation de l'édition (J9)."""
    deadline = settings.cancellation_deadline
    if deadline is not None and now < deadline:
        return settings.refund_percent_before
    return settings.refund_percent_after


def _refund_due(registration: Registration, percent: int) -> Decimal | None:
    paid = paid_amount(registration)
    if paid <= 0:
        return None
    return quantize(paid * Decimal(percent) / Decimal(100), registration.currency)


def cancel_by_participant(registration: Registration, *, actor: Actor) -> Registration:
    """Le participant annule : toujours une commande en attente ; une inscription confirmée
    jusqu'à la date limite d'annulation (sans date : par le CO seulement)."""
    ensure_editable(registration.edition)
    if registration.status == RegistrationStatus.PENDING:
        return workflow.transition(
            registration, RegistrationStatus.CANCELLED, actor=actor, reason="participant"
        )
    settings = registration_settings(registration.edition)
    now = timezone.now()
    deadline = settings.cancellation_deadline
    if registration.status == RegistrationStatus.CONFIRMED and (
        deadline is None or now >= deadline
    ):
        raise RuleViolation(
            _("La date limite d'annulation est passée : contactez le comité d'organisation."),
            code=ErrorCode.DEADLINE_PASSED,
        )
    return workflow.transition(
        registration,
        RegistrationStatus.CANCELLED,
        actor=actor,
        reason="participant",
        refund_due=_refund_due(registration, settings.refund_percent_before),
    )


def cancel_by_committee(
    registration: Registration, *, reason: str, actor: Actor, percent: int | None = None
) -> Registration:
    """Le CO annule (motif journalisé) ; part remboursée selon les règles de l'édition, ou
    celle qu'il fixe (0 à 100 %)."""
    ensure_editable(registration.edition)
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    if percent is None:
        percent = refund_percent(registration_settings(registration.edition), timezone.now())
    if not 0 <= percent <= 100:
        raise Invalid(fields={"refund_percent": [_("Pourcentage de 0 à 100.")]})
    refund = (
        _refund_due(registration, percent)
        if registration.status == RegistrationStatus.CONFIRMED
        else None
    )
    return workflow.transition(
        registration, RegistrationStatus.CANCELLED, actor=actor, reason=reason, refund_due=refund
    )


# --- Gratuité nominative (J4) ---------------------------------------------------------------------


@transaction.atomic
def grant_waiver(registration: Registration, *, reason: str, actor: Actor) -> Registration:
    """Le CO offre l'inscription en attente : ligne « gratuité » égale au total, puis
    confirmation. Motif obligatoire et journalisé."""
    ensure_editable(registration.edition)
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    registration = Registration.objects.select_for_update().get(pk=registration.pk)
    if registration.status != RegistrationStatus.PENDING or registration.total == 0:
        raise RuleViolation(
            _("Seule une inscription en attente de paiement peut être offerte."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    waiver = {
        "kind": LineKind.DISCOUNT,
        "code": "WAIVER",
        "label_fr": "Gratuité",
        "label_en": "Fee waiver",
        "amount": str(-registration.total),
    }
    before = {"total": str(registration.total), "method": registration.method}
    registration.lines = [*registration.lines, waiver]
    registration.total = Decimal(0)
    registration.method = PaymentMethod.WAIVER
    registration.save(update_fields=["lines", "total", "method", "updated_at"])
    record(
        "registration.waived",
        actor=actor,
        edition=registration.edition,
        obj=registration,
        before=before,
        after={"total": "0", "method": PaymentMethod.WAIVER},
        reason=reason,
    )
    return workflow.transition(
        registration, RegistrationStatus.CONFIRMED, actor=actor, reason=reason
    )


# --- Badge perdu (plan L7, K2) -------------------------------------------------------------------


@transaction.atomic
def regenerate_qr_token(registration: Registration, *, reason: str, actor: Actor) -> Registration:
    """Nouveau jeton QR pour une inscription confirmée (badge perdu) : l'ancien badge devient
    invalide, son empreinte est gardée (« badge remplacé » à l'accueil). Motif obligatoire,
    journal sans jeton."""
    ensure_editable(registration.edition)
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    registration = (
        Registration.objects.select_for_update().select_related("edition").get(pk=registration.pk)
    )
    if registration.status != RegistrationStatus.CONFIRMED or not registration.qr_token:
        raise RuleViolation(
            _("Seule une inscription confirmée a un badge."), code=ErrorCode.INVALID_TRANSITION
        )
    RetiredQrToken.objects.create(
        registration=registration,
        token_hash=token_hash(registration.qr_token),
        reason=RetiredTokenReason.REPLACED,
        retired_at=timezone.now(),
    )
    registration.qr_token = new_token()
    registration.save(update_fields=["qr_token", "updated_at"])
    record(
        "registration.qr_regenerated",
        actor=actor,
        edition=registration.edition,
        obj=registration,
        reason=reason,
    )
    return registration


# --- Identité de facturation et justificatif ------------------------------------------------------


@transaction.atomic
def update_billing(
    registration: Registration, data: Mapping[str, Any], *, actor: Actor
) -> Registration:
    """Identité de facturation, modifiable tant qu'aucune facture n'est émise (elle la fige)."""
    from apps.payments.models import BillingDocument, DocumentKind

    ensure_editable(registration.edition)
    registration = Registration.objects.select_for_update().get(pk=registration.pk)
    if registration.status not in ACTIVE_STATUSES:
        raise RuleViolation(_("Inscription annulée ou expirée."), code=ErrorCode.INVALID_TRANSITION)
    if BillingDocument.objects.filter(
        registration=registration, kind=DocumentKind.INVOICE
    ).exists():
        raise RuleViolation(
            _("Facture émise : l'identité de facturation ne change plus."),
            code=ErrorCode.SETTING_FROZEN,
        )
    changed = [
        name
        for name in BILLING_FIELDS
        if name in data and getattr(registration, name) != data[name]
    ]
    if not changed:
        return registration
    before = snapshot(registration)
    for name in changed:
        setattr(registration, name, data[name])
    registration.save(update_fields=[*changed, "updated_at"])
    after = snapshot(registration)
    record(
        "registration.billing_changed",
        actor=actor,
        edition=registration.edition,
        obj=registration,
        before={name: before[name] for name in changed},
        after={name: after[name] for name in changed},
    )
    return registration


@transaction.atomic
def upload_proof(
    registration: Registration, *, data: bytes, name: str, actor: Actor
) -> Registration:
    """Justificatif d'une catégorie qui l'exige (J2) : PDF, JPEG ou PNG de 5 Mo au plus, type
    vérifié par contenu, stocké hors racine web (règle n° 8). Remplace le précédent."""
    ensure_editable(registration.edition)
    registration = (
        Registration.objects.select_for_update().select_related("category").get(pk=registration.pk)
    )
    if not registration.category.requires_proof:
        raise Invalid(fields={"file": [_("Aucun justificatif demandé pour cette catégorie.")]})
    if registration.status not in ACTIVE_STATUSES:
        raise RuleViolation(_("Inscription annulée ou expirée."), code=ErrorCode.INVALID_TRANSITION)
    if len(data) > PROOF_MAX_BYTES:
        raise Invalid(fields={"file": [_("Fichier de 5 Mo au plus.")]})
    kind = sniff(data)
    if kind is None:
        raise Invalid(fields={"file": [_("PDF, JPEG ou PNG attendu.")]})
    previous = registration.proof_storage_name
    storage_name, _digest = PROOFS.write(data)
    registration.proof_storage_name = storage_name
    registration.proof_original_name = name[:255]
    registration.proof_kind = kind
    registration.proof_size = len(data)
    registration.proof_uploaded_at = timezone.now()
    registration.save(
        update_fields=[
            "proof_storage_name",
            "proof_original_name",
            "proof_kind",
            "proof_size",
            "proof_uploaded_at",
            "updated_at",
        ]
    )
    if previous:
        PROOFS.remove_after_commit(previous)
    record(
        "registration.proof_uploaded",
        actor=actor,
        edition=registration.edition,
        obj=registration,
        after={"kind": kind, "size": len(data)},
    )
    return registration


def known_proofs() -> list[str]:
    return list(
        Registration.objects.exclude(proof_storage_name="").values_list(
            "proof_storage_name", flat=True
        )
    )


# --- Expiration (J5, cron) ------------------------------------------------------------------------


def expire_overdue(now: dt.datetime | None = None) -> int:
    """Commandes en attente dont l'échéance est passée : expirées (places et code rendus).
    Idempotente : une inscription déjà expirée n'est plus « en attente »."""
    now = now or timezone.now()
    actor = Actor.command("cron:expire_registrations")
    count = 0
    overdue = Registration.objects.filter(
        status=RegistrationStatus.PENDING, due_at__isnull=False, due_at__lte=now
    ).values_list("pk", flat=True)
    for pk in list(overdue):
        registration = Registration.objects.get(pk=pk)
        if any(check(registration) for check in _EXPIRY_CHECKS):
            continue  # paiement peut-être en cours : prochain passage
        try:
            workflow.transition(registration, RegistrationStatus.EXPIRED, actor=actor)
        except RuleViolation:
            continue  # confirmée entre-temps (paiement reçu)
        count += 1
    return count


# --- RG-11 (J10) : personnes inscrites, pour le planificateur --------------------------------


def registered_people(edition: Edition) -> frozenset[str]:
    """Clés des personnes dont l'inscription est confirmée : ``user:<id>`` et
    ``email:<adresse>`` (adresse du compte et adresses vérifiées), pour reconnaître un
    présentateur par son compte ou par son adresse."""
    from allauth.account.models import EmailAddress

    rows = Registration.objects.filter(
        edition=edition, status=RegistrationStatus.CONFIRMED
    ).values_list("user_id", "user__email")
    keys = {f"user:{user_id}" for user_id, _email in rows}
    keys |= {f"email:{email.lower()}" for _user_id, email in rows if email}
    verified = EmailAddress.objects.filter(
        user_id__in=[user_id for user_id, _email in rows], verified=True
    ).values_list("email", flat=True)
    keys |= {f"email:{email.lower()}" for email in verified}
    return frozenset(keys)
