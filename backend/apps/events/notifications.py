"""E-mails du jour J et des attestations (plan L7, K11 ; étude, annexe A2 « Attestation
disponible »). Mis en file dans la transaction de l'émission, envoyés après validation
(règle n° 9). Ni PDF en pièce jointe ni code de vérification : un lien vers « Mes
documents »."""

from __future__ import annotations

from django.conf import settings
from django.utils import translation

from apps.accounts.services.roles import edition_title
from apps.communications.services import queue_email, register_email_template, resolve_locale
from apps.events.models import Certificate, DocumentNature, InvitationLetter, LetterStatus

CERTIFICATE_AVAILABLE = "events/email/certificate_available"
LETTER_ISSUED = "events/email/letter_issued"
LETTER_REFUSED = "events/email/letter_refused"
# « Mes documents » dans l'espace compte du portail (K15, L7.7).
MY_DOCUMENTS_PATH = "/compte/mes-documents"


def register_events_templates() -> None:
    for code in (CERTIFICATE_AVAILABLE, LETTER_ISSUED, LETTER_REFUSED):
        register_email_template(code)


def documents_link() -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}{MY_DOCUMENTS_PATH}"


def certificate_available(certificate: Certificate) -> None:
    user = certificate.user
    if not user.is_active or user.anonymized_at is not None:
        return
    locale = resolve_locale(None, user)
    with translation.override(locale):
        context = {
            "nature": str(DocumentNature(certificate.nature).label),
            "edition_title": edition_title(certificate.edition, locale),
            "link": documents_link(),
        }
    queue_email(
        template_code=CERTIFICATE_AVAILABLE,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=context,
        idempotency_key=f"certificate:{certificate.pk}",
    )


def letter_decided(letter: InvitationLetter) -> None:
    """Lettre émise (lien vers « Mes documents ») ou refusée (motif) : e-mail au demandeur."""
    user = letter.registration.user
    if not user.is_active or user.anonymized_at is not None:
        return
    locale = resolve_locale(None, user)
    issued = letter.status == LetterStatus.ISSUED
    queue_email(
        template_code=LETTER_ISSUED if issued else LETTER_REFUSED,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context={
            "edition_title": edition_title(letter.edition, locale),
            "reason": letter.refuse_reason,
            "link": documents_link(),
        },
        idempotency_key=f"letter:{letter.pk}:{letter.status}",
    )
