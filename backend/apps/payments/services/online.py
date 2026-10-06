"""Paiement en ligne (plan L6, J6 ; RG-15 ; bilan de L6.0).

- **Initiation** : une tentative = une ligne ``Payment`` et une référence unique. La ligne est
  créée et validée **avant** l'appel au fournisseur : aucun verrou n'est tenu pendant
  l'appel réseau. On garde l'empreinte du jeton de notification, jamais le jeton.
- **Notification** : signal seulement. Le jeton est comparé à temps constant à l'empreinte ;
  la confirmation ne vient que de l'**interrogation du statut** (``reconcile``). Chaque
  notification est enregistrée (en ajout seul) avec son issue. Rejouée, elle est sans effet
  (paiement déjà final). Fournisseur injoignable : une tâche reprend l'interrogation.
- **Retour du navigateur** : aucun effet (le portail affiche « paiement en cours »).
- **Réconciliation** : ``sync_payments`` (cron) interroge les paiements en cours ; avant
  d'expirer une commande, ses paiements en cours sont interrogés.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Profile
from apps.accounts.services.roles import ensure_editable
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import ErrorCode, RuleViolation
from apps.core.jobs import enqueue, register_job
from apps.payments.models import Payment, PaymentNotification, PaymentStatus
from apps.payments.providers import get_provider, online_provider
from apps.payments.providers.base import Customer, InvalidNotification, ProviderError
from apps.payments.services import documents
from apps.payments.services.manual import next_reference
from apps.registrations import workflow
from apps.registrations.models import PaymentMethod, Registration, RegistrationStatus
from apps.registrations.services.settings import registration_settings

IN_PROGRESS = (PaymentStatus.INITIATED, PaymentStatus.PENDING)
RECONCILE_JOB = "payments.reconcile"
SYSTEM = Actor.command("payments:reconcile")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _unavailable(reason) -> RuleViolation:
    return RuleViolation(reason, code=ErrorCode.PAYMENT_UNAVAILABLE)


def return_urls(payment: Payment) -> tuple[str, str]:
    """Retour du navigateur vers « Mon inscription » : simple affichage, aucun effet."""
    base = f"{settings.GESTCONF_PUBLIC_URL}/compte/inscription?paiement={payment.reference}"
    return base, f"{base}&echec=1"


def notify_url(provider_name: str) -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}/api/v1/payments/webhook/{provider_name}"


# --- Initiation -----------------------------------------------------------------------------------


def start_online_payment(
    registration: Registration, *, actor: Actor, language: str = "fr"
) -> tuple[Payment, str]:
    """Nouvelle tentative de paiement en ligne d'une inscription en attente ; renvoie le
    paiement et l'adresse de la page hébergée du fournisseur."""
    provider = online_provider()
    if provider is None or not registration_settings(registration.edition).online_enabled:
        raise _unavailable(_("Le paiement en ligne n'est pas proposé."))
    with transaction.atomic():
        ensure_editable(registration.edition)
        registration = (
            Registration.objects.select_for_update()
            .select_related("edition", "user")
            .get(pk=registration.pk)
        )
        if registration.status != RegistrationStatus.PENDING or registration.total <= 0:
            raise RuleViolation(
                _("Seule une inscription en attente de paiement peut être réglée."),
                code=ErrorCode.INVALID_TRANSITION,
            )
        reason = provider.supports(registration.currency, registration.total)
        if reason is not None:
            raise _unavailable(_("Paiement en ligne impossible : %(reason)s.") % {"reason": reason})
        if registration.method != PaymentMethod.ONLINE:
            registration.method = PaymentMethod.ONLINE
            registration.save(update_fields=["method", "updated_at"])
        payment = Payment.objects.create(
            registration=registration,
            provider=provider.name,
            method=PaymentMethod.ONLINE,
            reference=next_reference(registration),
            amount=registration.total,
            currency=registration.currency,
            status=PaymentStatus.INITIATED,
        )
    profile = Profile.objects.filter(user=registration.user).first()
    success_url, failed_url = return_urls(payment)
    try:
        initiation = provider.initiate(
            payment,
            customer=Customer(
                first_name=profile.first_name if profile else "",
                last_name=profile.last_name if profile else "",
                email=registration.user.email,
            ),
            designation=f"{registration.edition.code} {registration.reference}",
            language=language,
            success_url=success_url,
            failed_url=failed_url,
            notify_url=notify_url(provider.name),
        )
    except ProviderError as exc:
        Payment.objects.filter(pk=payment.pk).update(
            status=PaymentStatus.FAILED,
            provider_status="INIT_ERROR",
            completed_at=timezone.now(),
            note=str(exc)[:255],
        )
        raise _unavailable(
            _("Le service de paiement ne répond pas : réessayez plus tard.")
        ) from exc
    with transaction.atomic():
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        payment.provider_reference = initiation.provider_reference[:64]
        payment.notify_token_hash = token_hash(initiation.notify_token)
        payment.status = PaymentStatus.PENDING
        payment.save(
            update_fields=["provider_reference", "notify_token_hash", "status", "updated_at"]
        )
        record(
            "payment.initiated",
            actor=actor,
            edition=registration.edition,
            obj=payment,
            after={"reference": payment.reference, "amount": str(payment.amount)},
        )
    return payment, initiation.payment_url


# --- Notification (RG-15) -------------------------------------------------------------------------


def receive_notification(provider_name: str, data: dict) -> str:
    """Traite une notification ; renvoie son issue (journalisée) : ``unreadable``,
    ``unknown_payment``, ``invalid_token``, ``confirmed``, ``failed``, ``pending``,
    ``mismatch`` ou ``deferred``."""
    provider = get_provider(provider_name)
    now = timezone.now()
    try:
        notification = provider.parse_notification(data)
    except InvalidNotification:
        PaymentNotification.objects.create(
            provider=provider_name, received_at=now, outcome="unreadable"
        )
        return "unreadable"
    payment = Payment.objects.filter(
        provider=provider_name, reference=notification.reference
    ).first()
    valid = bool(
        payment is not None
        and payment.notify_token_hash
        and hmac.compare_digest(token_hash(notification.token), payment.notify_token_hash)
    )
    if payment is None or not valid:
        outcome = "unknown_payment" if payment is None else "invalid_token"
        PaymentNotification.objects.create(
            provider=provider_name,
            reference=notification.reference[:64],
            payment=payment,
            received_at=now,
            token_valid=False,
            outcome=outcome,
            body=notification.fields,
        )
        return outcome
    try:
        outcome = reconcile(payment)
    except ProviderError:
        enqueue(
            RECONCILE_JOB,
            {"payment_id": payment.pk},
            dedup_key=f"reconcile:{payment.pk}:{now:%Y%m%d%H%M}",
        )
        outcome = "deferred"
    PaymentNotification.objects.create(
        provider=provider_name,
        reference=notification.reference[:64],
        payment=payment,
        received_at=now,
        token_valid=True,
        outcome=outcome,
        body=notification.fields,
    )
    return outcome


# --- Réconciliation -------------------------------------------------------------------------------


def reconcile(payment: Payment) -> str:
    """Interroge le fournisseur (hors transaction) puis applique le statut. Idempotente : un
    paiement final n'est plus interrogé."""
    if payment.status not in IN_PROGRESS:
        return {PaymentStatus.SUCCEEDED: "confirmed"}.get(payment.status, "failed")
    provider = get_provider(payment.provider)
    if provider is None:
        raise ProviderError(f"fournisseur {payment.provider} non configuré")
    return apply_check(payment, provider.check(payment))


@transaction.atomic
def apply_check(payment: Payment, check) -> str:
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    if payment.status not in IN_PROGRESS:
        return {PaymentStatus.SUCCEEDED: "confirmed"}.get(payment.status, "failed")
    now = timezone.now()
    payment.last_checked_at = now
    payment.provider_status = check.provider_status[:32]
    fields = ["last_checked_at", "provider_status", "updated_at"]
    edition = payment.registration.edition
    if check.outcome == "succeeded":
        mismatch = (check.amount is not None and check.amount != payment.amount) or (
            check.currency is not None and check.currency != payment.currency
        )
        if check.provider_reference and payment.provider_reference:
            mismatch = mismatch or check.provider_reference != payment.provider_reference
        if mismatch:
            payment.note = "Montant, devise ou référence différents : à vérifier."
            payment.save(update_fields=[*fields, "note"])
            record("payment.mismatch", actor=SYSTEM, edition=edition, obj=payment)
            return "mismatch"
        payment.status = PaymentStatus.SUCCEEDED
        payment.completed_at = now
        payment.save(update_fields=[*fields, "status", "completed_at"])
        record(
            "payment.succeeded",
            actor=SYSTEM,
            edition=edition,
            obj=payment,
            after={"reference": payment.reference, "amount": str(payment.amount)},
        )
        registration = Registration.objects.select_for_update().get(pk=payment.registration_id)
        if registration.status == RegistrationStatus.PENDING:
            workflow.transition(registration, RegistrationStatus.CONFIRMED, actor=SYSTEM)
            documents.issue_invoice(registration, payment, actor=SYSTEM)
        else:
            # Payé alors que l'inscription n'attend plus de paiement (expirée, annulée, déjà
            # réglée) : rien d'automatique, le CO rembourse ou rattache.
            Payment.objects.filter(pk=payment.pk).update(
                note="Paiement reçu hors attente : à rembourser ou à rattacher."
            )
            record("payment.orphan", actor=SYSTEM, edition=edition, obj=payment)
        return "confirmed"
    if check.outcome == "failed":
        payment.status = PaymentStatus.FAILED
        payment.completed_at = now
        payment.save(update_fields=[*fields, "status", "completed_at"])
        record("payment.failed", actor=SYSTEM, edition=edition, obj=payment)
        return "failed"
    payment.save(update_fields=fields)
    return "pending"


@register_job(RECONCILE_JOB)
def reconcile_job(job) -> None:
    """Reprise d'une interrogation après une notification (fournisseur injoignable) ; une
    erreur relance la tâche selon la politique de la file."""
    payment = Payment.objects.filter(pk=job.payload.get("payment_id")).first()
    if payment is not None:
        reconcile(payment)


def check_latest(registration: Registration) -> str:
    """Le participant revient de la page de paiement : interroge sa dernière tentative en
    cours (sans effet si aucune)."""
    payment = (
        Payment.objects.filter(registration=registration, status__in=IN_PROGRESS)
        .order_by("-created_at", "-id")
        .first()
    )
    if payment is None:
        return "none"
    try:
        return reconcile(payment)
    except ProviderError:
        return "pending"


def sync_payments(
    now: dt.datetime | None = None,
    *,
    settle_after: dt.timedelta = dt.timedelta(minutes=10),
    abandon_after: dt.timedelta = dt.timedelta(days=7),
) -> dict[str, int]:
    """Cron : interroge les paiements en ligne en cours depuis plus de ``settle_after`` ;
    une tentative toujours en cours au-delà d'``abandon_after`` est abandonnée."""
    now = now or timezone.now()
    counts = {"checked": 0, "errors": 0, "abandoned": 0}
    rows = Payment.objects.filter(status__in=IN_PROGRESS, created_at__lte=now - settle_after)
    for payment in rows.exclude(provider="manual").order_by("created_at"):
        try:
            outcome = reconcile(payment)
        except ProviderError:
            counts["errors"] += 1
            continue
        counts["checked"] += 1
        if outcome == "pending" and payment.created_at <= now - abandon_after:
            Payment.objects.filter(pk=payment.pk, status__in=IN_PROGRESS).update(
                status=PaymentStatus.CANCELLED, completed_at=now, provider_status="ABANDONED"
            )
            counts["abandoned"] += 1
    return counts


def postpone_expiry(registration: Registration) -> bool:
    """Effet d'expiration (J5) : avant d'expirer une commande, ses paiements en ligne en cours
    sont interrogés. On reporte l'expiration si le fournisseur ne répond pas, ou si une
    tentative de moins de deux heures est encore en cours (paiement peut-être en train)."""
    now = timezone.now()
    for payment in Payment.objects.filter(registration=registration, status__in=IN_PROGRESS):
        try:
            outcome = reconcile(payment)
        except ProviderError:
            return True
        if outcome == "pending" and payment.created_at > now - dt.timedelta(hours=2):
            return True
    return False
