"""E-mails des inscriptions (plan L6, J5, J11). Mis en file dans la transaction de
l'opération, envoyés après validation (règle n° 9). Ni facture ni QR en pièce jointe : un
lien vers « Mon inscription » (J11). Objets sans autre variable que le nom du site."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation

from apps.accounts.services.roles import edition_title
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.core.money import format_amount
from apps.registrations.models import PaymentMethod, Registration, RegistrationStatus
from apps.submissions.notifications import local_datetime

ORDERED = "registrations/email/ordered"
CONFIRMED = "registrations/email/confirmed"
CANCELLED = "registrations/email/cancelled"
EXPIRED = "registrations/email/expired"


def register_registration_templates() -> None:
    for code in (ORDERED, CONFIRMED, CANCELLED, EXPIRED):
        register_email_template(code)


def registration_link() -> str:
    """« Mon inscription » dans l'espace compte du portail (J13)."""
    return f"{settings.GESTCONF_PUBLIC_URL}/compte/inscription"


def _context(registration: Registration, locale: str) -> dict[str, str]:
    edition = registration.edition
    with translation.override(locale):
        method = PaymentMethod(registration.method).label
        return {
            "reference": registration.reference,
            "edition_title": edition_title(edition, locale),
            "total": format_amount(registration.total, registration.currency, locale),
            "method": str(method),
            "due": local_datetime(registration.due_at, edition.timezone, locale)
            if registration.due_at
            else "",
            "refund": format_amount(registration.refund_due, registration.currency, locale)
            if registration.refund_due
            else "",
            "link": registration_link(),
        }


def _send(registration: Registration, template: str, key: str) -> None:
    user = registration.user
    if not user.is_active or user.anonymized_at is not None:
        return
    locale = resolve_locale(None, user)
    queue_email(
        template_code=template,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=_context(registration, locale),
        idempotency_key=f"registration-{key}:{registration.pk}",
    )


def ordered(registration: Registration) -> None:
    """Commande enregistrée, en attente de paiement : montant, moyen et échéance."""
    _send(registration, ORDERED, "ordered")


def status_changed(registration: Registration, from_status: str) -> None:
    if registration.status == RegistrationStatus.CONFIRMED:
        _send(registration, CONFIRMED, "confirmed")
    elif registration.status == RegistrationStatus.CANCELLED:
        _send(registration, CANCELLED, "cancelled")
    elif registration.status == RegistrationStatus.EXPIRED:
        _send(registration, EXPIRED, "expired")
