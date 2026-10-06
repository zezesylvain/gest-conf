"""Lettres d'invitation (plan L7, K12, K14 ; étude M10).

Le participant demande sa lettre depuis « Mon inscription » (inscription en attente ou
confirmée) : nom tel que sur le passeport, nationalité, numéro de passeport, dates de séjour,
ambassade ou consulat. Le CO (``letters.manage``) l'instruit : **émise** (PDF figé, signé
comme une attestation, vérifiable publiquement) ou **refusée** (motif). Une lettre émise se
révoque (motif, journal). La lettre précise qu'elle n'engage pas la prise en charge des
frais.

Le numéro de passeport n'est jamais journalisé ; il est effacé à l'anonymisation du compte
et 30 jours après la fin de l'édition (ou à son archivage), tâche de conservation (K14).
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import EditionStatus
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.private_files import PrivateStore
from apps.events import documents, signing
from apps.events.models import DocumentNature, InvitationLetter, LetterStatus, SigningMode
from apps.events.services import certificates
from apps.registrations.models import ACTIVE_STATUSES, Registration

if TYPE_CHECKING:
    from apps.core.actor import Actor

PDFS = PrivateStore("letters")
MAX_STAY = dt.timedelta(days=90)
# Effacement du numéro de passeport : 30 jours après la fin de l'édition (K14).
PASSPORT_RETENTION = dt.timedelta(days=30)
REQUEST_FIELDS = (
    "passport_name",
    "nationality",
    "passport_number",
    "stay_from",
    "stay_to",
    "embassy",
)


def active_key(registration: Registration) -> str:
    return str(registration.pk)


def current_letter(registration: Registration) -> InvitationLetter | None:
    """Dernière demande de l'inscription (en cours, émise, refusée ou révoquée)."""
    return (
        InvitationLetter.objects.filter(registration=registration)
        .order_by("-created_at", "-id")
        .first()
    )


@transaction.atomic
def request_letter(
    registration: Registration, data: dict[str, Any], *, actor: Actor
) -> InvitationLetter:
    """Demande du participant : inscription en attente ou confirmée ; une demande en cours ou
    une lettre émise à la fois ; séjour de 90 jours au plus."""
    registration = (
        Registration.objects.select_for_update().select_related("edition").get(pk=registration.pk)
    )
    ensure_editable(registration.edition)
    if registration.status not in ACTIVE_STATUSES:
        raise RuleViolation(
            _("Inscription annulée ou expirée : aucune lettre possible."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    values = {name: data[name] for name in REQUEST_FIELDS}
    for name in ("passport_name", "nationality", "passport_number", "embassy"):
        values[name] = values[name].strip()
    if values["stay_to"] < values["stay_from"]:
        raise Invalid(fields={"stay_to": [_("Le départ suit l'arrivée.")]})
    if values["stay_to"] - values["stay_from"] > MAX_STAY:
        raise Invalid(fields={"stay_to": [_("Séjour de 90 jours au plus.")]})
    try:
        with transaction.atomic():
            letter = InvitationLetter.objects.create(
                edition=registration.edition,
                registration=registration,
                active_key=active_key(registration),
                **values,
            )
    except IntegrityError as error:
        raise RuleViolation(
            _("Une demande est déjà en cours, ou une lettre déjà émise."),
            code=ErrorCode.INVALID_TRANSITION,
        ) from error
    record(
        "letter.requested",
        actor=actor,
        edition=registration.edition,
        obj=letter,
        after=snapshot(letter),
    )
    return letter


def _locked(letter: InvitationLetter, *, expected: str) -> InvitationLetter:
    letter = (
        InvitationLetter.objects.select_for_update()
        .select_related("edition", "registration__user__profile", "registration__edition")
        .get(pk=letter.pk)
    )
    ensure_editable(letter.edition)
    if letter.status != expected:
        raise RuleViolation(
            _("Changement de statut impossible depuis « %(status)s ».")
            % {"status": LetterStatus(letter.status).label},
            code=ErrorCode.INVALID_TRANSITION,
        )
    return letter


def _values(letter: InvitationLetter, language: str) -> dict[str, str]:
    return {
        "name": certificates.person_name(letter.registration.user),
        **certificates.edition_values(letter.edition, language),
        "passport_name": letter.passport_name,
        "nationality": letter.nationality,
        "passport": letter.passport_number,
        "stay": certificates.date_range(letter.stay_from, letter.stay_to, language),
        "embassy": letter.embassy,
    }


def render_letter(
    context: certificates.IssueContext, letter: InvitationLetter, *, code: str, at
) -> bytes:
    from apps.events import texts

    words = context.template.texts
    values_fr, values_en = _values(letter, "fr"), _values(letter, "en")
    signature = context.signature
    data = documents.DocumentData(
        document_title=f"{texts.fill(words['title_fr'], values_fr)} · {letter.passport_name}",
        edition_title=values_fr["edition"],
        title_fr=texts.fill(words["title_fr"], values_fr),
        title_en=texts.fill(words["title_en"], values_en),
        body_fr=texts.fill(words["body_fr"], values_fr),
        body_en=texts.fill(words["body_en"], values_en),
        footer_fr=texts.fill(words["footer_fr"], values_fr),
        footer_en=texts.fill(words["footer_en"], values_en),
        issued_at=at,
        timezone=letter.edition.timezone,
        signatory_name=signature.display_name,
        signatory_title_fr=signature.title_fr,
        signatory_title_en=signature.title_en,
        signature_png=context.signature_png,
        header_png=context.header_png,
        verification_url=certificates.verification_url(code),
        signature_right=context.settings.layout == "signature_right",
        landscape=False,
    )
    pdf = documents.render(data)
    if context.key is not None:
        pdf = signing.sign_pdf(
            pdf,
            context.key,
            reason=str(_("Lettre d'invitation délivrée par GEST-CONF")),
            location=values_fr["venue"] or letter.edition.code,
        )
    return pdf


def issue_letter(letter: InvitationLetter, *, actor: Actor) -> InvitationLetter:
    """Émission par le CO : signataire désigné pour les lettres, PDF figé et vérifiable,
    e-mail au participant."""
    from apps.events import notifications

    with transaction.atomic():
        letter = _locked(letter, expected=LetterStatus.REQUESTED)
        if letter.registration.status not in ACTIVE_STATUSES:
            raise RuleViolation(
                _("Inscription annulée ou expirée : aucune lettre possible."),
                code=ErrorCode.INVALID_TRANSITION,
            )
        context = certificates.document_context(letter.edition, DocumentNature.LETTER, actor.user)
        code = certificates.new_code()
        now = timezone.now()
        pdf = render_letter(context, letter, code=code, at=now)
        before = snapshot(letter)
        storage_name, digest = PDFS.write(pdf)
        letter.status = LetterStatus.ISSUED
        letter.decided_at = letter.issued_at = now
        letter.decided_by = actor.user
        letter.verification_code = code
        letter.storage_name, letter.sha256, letter.size = storage_name, digest, len(pdf)
        letter.signing_mode = SigningMode.PADES if context.key is not None else SigningMode.IMAGE
        letter.signatory_name = context.signature.display_name
        letter.signatory_title_fr = context.signature.title_fr
        letter.signatory_title_en = context.signature.title_en
        letter.signature_sha256 = context.signature.image_sha256
        letter.save()
        record(
            "letter.issued",
            actor=actor,
            edition=letter.edition,
            obj=letter,
            before=before,
            after=snapshot(letter),
        )
        notifications.letter_decided(letter)
    return letter


@transaction.atomic
def refuse_letter(letter: InvitationLetter, *, reason: str, actor: Actor) -> InvitationLetter:
    from apps.events import notifications

    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    letter = _locked(letter, expected=LetterStatus.REQUESTED)
    before = snapshot(letter)
    letter.status = LetterStatus.REFUSED
    letter.decided_at = timezone.now()
    letter.decided_by = actor.user
    letter.refuse_reason = reason.strip()[:500]
    letter.active_key = None
    letter.save()
    record(
        "letter.refused",
        actor=actor,
        edition=letter.edition,
        obj=letter,
        before=before,
        after=snapshot(letter),
        reason=reason,
    )
    notifications.letter_decided(letter)
    return letter


@transaction.atomic
def revoke_letter(letter: InvitationLetter, *, reason: str, actor: Actor) -> InvitationLetter:
    """Révocation d'une lettre émise (RG-17) : la vérification répond « révoquée »."""
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    letter = _locked(letter, expected=LetterStatus.ISSUED)
    before = snapshot(letter)
    letter.status = LetterStatus.REVOKED
    letter.revoked_at = timezone.now()
    letter.revoked_by = actor.user
    letter.revoke_reason = reason.strip()[:500]
    letter.active_key = None
    letter.save()
    record(
        "letter.revoked",
        actor=actor,
        edition=letter.edition,
        obj=letter,
        before=before,
        after=snapshot(letter),
        reason=reason,
    )
    return letter


def pdf_bytes(letter: InvitationLetter) -> bytes:
    return PDFS.read(letter.storage_name)


def verify(code: str) -> dict[str, Any] | None:
    """Vérification publique d'une lettre (K10) : nom du passeport, sauf compte anonymisé."""
    letter = (
        InvitationLetter.objects.select_related("edition", "registration__user")
        .filter(verification_code=code, status__in=(LetterStatus.ISSUED, LetterStatus.REVOKED))
        .first()
    )
    if letter is None:
        return None
    edition = letter.edition
    return {
        "kind": "letter",
        "nature": DocumentNature.LETTER,
        "name": None if letter.registration.user.anonymized_at else letter.passport_name,
        "edition_title_fr": edition.title_fr,
        "edition_title_en": edition.title_en or edition.title_fr,
        "edition_start": edition.start_date,
        "edition_end": edition.end_date,
        "issued_at": letter.issued_at,
        "status": "revoked" if letter.revoked_at else "valid",
        "revoked_at": letter.revoked_at,
    }


def masked_number(number: str) -> str:
    """« ••••••789 » : jamais le numéro entier hors de l'instruction."""
    if not number:
        return ""
    return "•" * max(0, len(number) - 3) + number[-3:]


def erase_passport_numbers(dry_run: bool, now) -> int:
    """Tâche de conservation (K14) : numéros des éditions archivées ou finies depuis 30 jours."""
    limit = (now - PASSPORT_RETENTION).date()
    rows = InvitationLetter.objects.exclude(passport_number="").filter(
        Q(edition__status=EditionStatus.ARCHIVED) | Q(edition__end_date__lt=limit)
    )
    count = rows.count()
    if not dry_run and count:
        rows.update(passport_number="", passport_erased_at=now)
    return count


def known_files() -> list[str]:
    return list(
        InvitationLetter.objects.exclude(storage_name="").values_list("storage_name", flat=True)
    )
