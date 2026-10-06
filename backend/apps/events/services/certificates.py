"""Attestations (plan L7, K9 à K11, K14, K18, K19 ; RG-16, RG-17).

**RG-16** : une attestation n'existe que sur condition vérifiée **à l'émission** :

- **participation** : inscription confirmée **et** présence enregistrée (accueil ou
  session) ;
- **communication** : présentateur d'une communication ``PRESENTED`` (une par
  présentateur ; titre et référence figés) ;
- **évaluation** : relecteur ayant envoyé au moins une évaluation (nombre seulement, jamais
  les titres : RG-04) ; nature activable par édition, désactivée par défaut.

Émission par le CO (``certificates.manage``) : tâche ``events.issue_certificates`` (règle
n° 9), par lots de 100, idempotente (une attestation active par personne, nature et objet),
relancée tant qu'il reste des personnes. Rien ne s'émet sans signataire désigné, dont la
signature est complète et le rôle actif (K18).

Chaque attestation est **figée** : PDF privé et son empreinte, nom, institution, signataire,
empreinte de l'image de signature, code de vérification public. Révocable (motif, journal),
jamais supprimée.
"""

from __future__ import annotations

import base64
import re
import secrets
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.conf import settings as django_settings
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.invitations import display_name
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record, snapshot
from apps.core.errors import DomainError, ErrorCode, Invalid, RuleViolation
from apps.core.jobs import enqueue, register_job
from apps.core.models import Job, JobStatus
from apps.core.private_files import PrivateStore
from apps.events import documents, signing, texts
from apps.events.models import (
    CERTIFICATE_NATURES,
    Certificate,
    CertificateSettings,
    Checkin,
    DocumentNature,
    DocumentTemplate,
    Signature,
    SignatureLayout,
    SigningMode,
)
from apps.events.services import signatures
from apps.registrations.models import Registration, RegistrationStatus
from apps.submissions.models import Submission, SubmissionStatus

if TYPE_CHECKING:
    from apps.accounts.models import User as UserType

PDFS = PrivateStore("certificates")
HEADERS = PrivateStore("certificate-headers")
KEYS = PrivateStore("signing-keys")
ISSUE_JOB = "events.issue_certificates"
ISSUE_BATCH = 100
SYSTEM = Actor.system("job:certificates")
# Code de vérification : 128 bits en base32 (RFC 4648, sans remplissage), 26 caractères.
CODE_PATTERN = re.compile(r"^[A-Z2-7]{26}$")
VERIFICATION_PATH = "/verification/"
SETTINGS_FIELDS = ("signing_mode", "review_enabled", "layout")
HEADER_MAX_SIDE, HEADER_MIN_WIDTH, HEADER_MIN_HEIGHT = 2400, 200, 40


# --- Paramètres et gabarits (K19) ---------------------------------------------------------------


def certificate_settings(edition: Edition) -> CertificateSettings:
    found, _created = CertificateSettings.objects.get_or_create(edition=edition)
    return found


def signing_available() -> bool:
    return any(key.strip() for key in django_settings.GESTCONF_SIGNING_ENCRYPTION_KEYS)


@transaction.atomic
def update_settings(edition: Edition, data: dict[str, Any], *, actor: Actor) -> CertificateSettings:
    ensure_editable(edition)
    unknown = set(data) - set(SETTINGS_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    current = CertificateSettings.objects.select_for_update().get(
        pk=certificate_settings(edition).pk
    )
    mode = data.get("signing_mode", current.signing_mode)
    if mode == SigningMode.PROVIDER:
        raise signing.unavailable(
            _("Aucun prestataire de signature qualifiée n'est branché (question Q17).")
        )
    if mode == SigningMode.PADES and mode != current.signing_mode:
        _check_key(current)
    before = snapshot(current)
    for name, value in data.items():
        setattr(current, name, value)
    current.save()
    record(
        "certificates.settings_updated",
        actor=actor,
        edition=edition,
        obj=current,
        before=before,
        after=snapshot(current),
    )
    return current


def _check_key(current: CertificateSettings) -> None:
    if not current.key_storage_name:
        raise signing.unavailable(_("Déposez d'abord le certificat de signature de l'institution."))
    if current.key_not_after is not None and current.key_not_after <= timezone.now():
        raise signing.unavailable(_("Le certificat de signature a expiré."))
    signing.check_key(KEYS.read(current.key_storage_name))


@transaction.atomic
def upload_header(edition: Edition, *, data: bytes, actor: Actor) -> CertificateSettings:
    """En-tête du modèle officiel (logo ou bandeau de l'institution), réencodé en PNG."""
    ensure_editable(edition)
    png, width, height = signatures.normalize_image(
        data, max_side=HEADER_MAX_SIDE, min_width=HEADER_MIN_WIDTH, min_height=HEADER_MIN_HEIGHT
    )
    current = CertificateSettings.objects.select_for_update().get(
        pk=certificate_settings(edition).pk
    )
    before = snapshot(current)
    previous = current.header_storage_name
    current.header_storage_name, current.header_sha256 = HEADERS.write(png)
    current.header_width, current.header_height = width, height
    current.save()
    if previous:
        HEADERS.remove_after_commit(previous)
    record(
        "certificates.header_uploaded",
        actor=actor,
        edition=edition,
        obj=current,
        before=before,
        after=snapshot(current),
    )
    return current


@transaction.atomic
def delete_header(edition: Edition, *, actor: Actor) -> CertificateSettings:
    ensure_editable(edition)
    current = CertificateSettings.objects.select_for_update().get(
        pk=certificate_settings(edition).pk
    )
    if current.header_storage_name:
        before = snapshot(current)
        HEADERS.remove_after_commit(current.header_storage_name)
        current.header_storage_name = current.header_sha256 = ""
        current.header_width = current.header_height = None
        current.save()
        record(
            "certificates.header_deleted",
            actor=actor,
            edition=edition,
            obj=current,
            before=before,
            after=snapshot(current),
        )
    return current


@transaction.atomic
def upload_signing_key(
    edition: Edition, *, data: bytes, password: str, actor: Actor
) -> CertificateSettings:
    """Certificat PAdES de l'institution (K19) : ouvert, puis rechiffré ; mot de passe oublié."""
    ensure_editable(edition)
    prepared = signing.prepare_key(data, password)
    current = CertificateSettings.objects.select_for_update().get(
        pk=certificate_settings(edition).pk
    )
    before = snapshot(current)
    previous = current.key_storage_name
    current.key_storage_name, _digest = KEYS.write(prepared.encrypted)
    current.key_subject = prepared.subject
    current.key_not_after = prepared.not_after
    current.key_uploaded_at = timezone.now()
    current.save()
    if previous:
        KEYS.remove_after_commit(previous)
    record(
        "certificates.signing_key_uploaded",
        actor=actor,
        edition=edition,
        obj=current,
        before=before,
        after=snapshot(current),
    )
    return current


@transaction.atomic
def delete_signing_key(edition: Edition, *, actor: Actor) -> CertificateSettings:
    """Retrait du certificat : la signature revient à l'image seule."""
    ensure_editable(edition)
    current = CertificateSettings.objects.select_for_update().get(
        pk=certificate_settings(edition).pk
    )
    if current.key_storage_name:
        before = snapshot(current)
        KEYS.remove_after_commit(current.key_storage_name)
        current.key_storage_name = current.key_subject = ""
        current.key_not_after = current.key_uploaded_at = None
        if current.signing_mode == SigningMode.PADES:
            current.signing_mode = SigningMode.IMAGE
        current.save()
        record(
            "certificates.signing_key_deleted",
            actor=actor,
            edition=edition,
            obj=current,
            before=before,
            after=snapshot(current),
        )
    return current


def _active_signatory(signature: Signature | None) -> bool:
    return (
        signature is not None
        and signature.is_complete
        and UserRole.objects.filter(
            edition_id=signature.edition_id,
            user_id=signature.user_id,
            role=Role.SIGNATORY,
            status=UserRoleStatus.ACTIVE,
        ).exists()
    )


def signatories(edition: Edition) -> list[Signature]:
    """Signatures désignables : complètes, de comptes au rôle de signataire actif (K18)."""
    active = UserRole.objects.filter(
        edition=edition, role=Role.SIGNATORY, status=UserRoleStatus.ACTIVE
    ).values_list("user_id", flat=True)
    rows = Signature.objects.filter(edition=edition, user_id__in=active).select_related(
        "user__profile"
    )
    return [row for row in rows.order_by("display_name", "id") if row.is_complete]


@dataclass(frozen=True, slots=True)
class TemplateView:
    nature: str
    texts: dict[str, str]
    customized: dict[str, bool]
    signatory: Signature | None


def template_for(edition: Edition, nature: str) -> TemplateView:
    row = (
        DocumentTemplate.objects.select_related("signatory")
        .filter(edition=edition, nature=nature)
        .first()
    )
    defaults = texts.DEFAULTS[nature]
    values = {}
    customized = {}
    for field in texts.TEXT_FIELDS:
        own = getattr(row, field, "") if row is not None else ""
        values[field] = own or defaults[field]
        customized[field] = bool(own)
    return TemplateView(nature, values, customized, row.signatory if row is not None else None)


@transaction.atomic
def update_template(edition: Edition, nature: str, data: dict[str, Any], *, actor: Actor):
    """Textes FR et EN (variables fermées) et signataire désigné d'une nature. Un texte vide
    rétablit le texte par défaut."""
    ensure_editable(edition)
    if nature not in DocumentNature.values:
        raise Invalid(fields={"nature": [_("Nature inconnue.")]})
    errors: dict[str, list[str]] = {}
    for field in texts.TEXT_FIELDS:
        if field in data:
            found = texts.placeholder_errors(data[field], nature)
            if found:
                errors[field] = found
    signatory = None
    if "signatory" in data and data["signatory"] is not None:
        signatory = Signature.objects.filter(edition=edition, pk=data["signatory"]).first()
        if not _active_signatory(signatory):
            errors["signatory"] = [
                str(_("Signataire de l'édition, au rôle actif et à la signature complète."))
            ]
    if errors:
        raise Invalid(fields=errors)
    row, _created = DocumentTemplate.objects.select_for_update().get_or_create(
        edition=edition, nature=nature
    )
    before = snapshot(row)
    for field in texts.TEXT_FIELDS:
        if field in data:
            setattr(row, field, data[field].strip())
    if "signatory" in data:
        row.signatory = signatory
    row.full_clean(exclude=["edition", "signatory"])
    row.save()
    record(
        "certificates.template_updated",
        actor=actor,
        edition=edition,
        obj=row,
        before=before,
        after=snapshot(row),
    )
    return template_for(edition, nature)


# --- Valeurs des textes ---------------------------------------------------------------------------


def edition_dates(edition: Edition, language: str) -> str:
    """« du 1er au 3 juin 2027 », « from June 1 to 3, 2027 » ; vide sans dates."""
    start, end = edition.start_date, edition.end_date or edition.start_date
    if start is None:
        return ""
    fr_day = lambda day: "1er" if day.day == 1 else str(day.day)  # noqa: E731
    months_fr, months_en = documents.MONTHS_FR, documents.MONTHS_EN
    if language == "fr":
        if start == end:
            return f"le {fr_day(start)} {months_fr[start.month - 1]} {start.year}"
        if (start.year, start.month) == (end.year, end.month):
            return f"du {fr_day(start)} au {fr_day(end)} {months_fr[end.month - 1]} {end.year}"
        if start.year == end.year:
            return (
                f"du {fr_day(start)} {months_fr[start.month - 1]} au {fr_day(end)} "
                f"{months_fr[end.month - 1]} {end.year}"
            )
        return (
            f"du {fr_day(start)} {months_fr[start.month - 1]} {start.year} au {fr_day(end)} "
            f"{months_fr[end.month - 1]} {end.year}"
        )
    if start == end:
        return f"on {months_en[start.month - 1]} {start.day}, {start.year}"
    if (start.year, start.month) == (end.year, end.month):
        return f"from {months_en[start.month - 1]} {start.day} to {end.day}, {end.year}"
    if start.year == end.year:
        return (
            f"from {months_en[start.month - 1]} {start.day} to {months_en[end.month - 1]} "
            f"{end.day}, {end.year}"
        )
    return (
        f"from {months_en[start.month - 1]} {start.day}, {start.year} to "
        f"{months_en[end.month - 1]} {end.day}, {end.year}"
    )


def edition_values(edition: Edition, language: str) -> dict[str, str]:
    title = edition.title_en if language == "en" and edition.title_en else edition.title_fr
    return {
        "edition": title,
        "dates": edition_dates(edition, language),
        "venue": ", ".join(part for part in (edition.venue, edition.city) if part),
    }


def person_name(user: UserType) -> str:
    profile = getattr(user, "profile", None)
    if profile is not None and (profile.first_name or profile.last_name):
        return f"{profile.first_name} {profile.last_name}".strip()
    return display_name(user)


# --- Éligibilité (RG-16) -------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Candidate:
    user: UserType
    submission: Submission | None
    details: dict[str, Any]

    def active_key(self, edition: Edition, nature: str) -> str:
        return Certificate.make_active_key(
            edition.pk, self.user.pk, nature, self.submission.pk if self.submission else None
        )


@dataclass(frozen=True, slots=True)
class Eligibility:
    candidates: list[Candidate]
    unreachable: int  # présentateurs sans compte (attestation impossible à remettre)


def _participants(edition: Edition) -> Eligibility:
    present = Checkin.objects.filter(edition=edition, active_key__isnull=False).values(
        "registration_id"
    )
    rows = (
        Registration.objects.filter(
            edition=edition, status=RegistrationStatus.CONFIRMED, pk__in=present
        )
        .select_related("user__profile")
        .order_by("id")
    )
    return Eligibility([Candidate(row.user, None, {}) for row in rows], 0)


def _account_of(author) -> UserType | None:
    if author.user_id:
        return author.user
    from allauth.account.models import EmailAddress

    found = (
        EmailAddress.objects.filter(email__iexact=author.email, verified=True)
        .select_related("user__profile")
        .first()
    )
    return found.user if found is not None else None


def _presenters(edition: Edition) -> Eligibility:
    from apps.program.services.planning import presenters

    rows = (
        Submission.objects.filter(edition=edition, status=SubmissionStatus.PRESENTED)
        .prefetch_related("authors__user__profile")
        .select_related("presentation_confirmation")
        .order_by("id")
    )
    candidates, unreachable, seen = [], 0, set()
    for submission in rows:
        for author in presenters(submission):
            user = _account_of(author)
            if user is None:
                unreachable += 1
                continue
            if (user.pk, submission.pk) in seen:
                continue
            seen.add((user.pk, submission.pk))
            details = {"title": submission.title, "reference": submission.reference}
            candidates.append(Candidate(user, submission, details))
    return Eligibility(candidates, unreachable)


def _reviewers(edition: Edition) -> Eligibility:
    from apps.reviews.models import Review, ReviewStatus

    counts = (
        Review.objects.filter(
            status=ReviewStatus.SUBMITTED, assignment__submission__edition=edition
        )
        .values("assignment__reviewer")
        .annotate(count=Count("pk"))
    )
    by_user = {row["assignment__reviewer"]: row["count"] for row in counts}
    users = User.objects.filter(pk__in=by_user).select_related("profile").order_by("id")
    return Eligibility([Candidate(user, None, {"count": by_user[user.pk]}) for user in users], 0)


def eligibility(edition: Edition, nature: str) -> Eligibility:
    if nature == DocumentNature.PARTICIPATION:
        return _participants(edition)
    if nature == DocumentNature.PRESENTATION:
        return _presenters(edition)
    if nature == DocumentNature.REVIEW:
        return _reviewers(edition)
    raise Invalid(fields={"nature": [_("Nature d'attestation inconnue.")]})


# --- Préparation et émission (K11) ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IssueContext:
    edition: Edition
    nature: str
    settings: CertificateSettings
    template: TemplateView
    signature: Signature
    signature_png: bytes
    header_png: bytes | None
    key: bytes | None
    requested_by: UserType | None


def preflight(edition: Edition, nature: str, requested_by: UserType | None = None) -> IssueContext:
    """Conditions de l'émission : nature activée, signataire désigné (signature complète,
    rôle actif), signature PAdES disponible si elle est choisie. Rien n'est écrit."""
    ensure_editable(edition)
    if nature not in CERTIFICATE_NATURES:
        raise Invalid(fields={"nature": [_("Nature d'attestation inconnue.")]})
    current = certificate_settings(edition)
    if nature == DocumentNature.REVIEW and not current.review_enabled:
        raise Invalid(fields={"nature": [_("Attestation d'évaluation désactivée pour l'édition.")]})
    template = template_for(edition, nature)
    if not _active_signatory(template.signatory):
        raise RuleViolation(
            _("Aucun signataire désigné, ou sa signature est incomplète."),
            code=ErrorCode.SIGNATORY_MISSING,
        )
    key = None
    if current.signing_mode == SigningMode.PROVIDER:
        raise signing.unavailable(_("Aucun prestataire de signature qualifiée n'est branché."))
    if current.signing_mode == SigningMode.PADES:
        _check_key(current)
        key = KEYS.read(current.key_storage_name)
    return IssueContext(
        edition=edition,
        nature=nature,
        settings=current,
        template=template,
        signature=template.signatory,
        signature_png=signatures.image_bytes(template.signatory),
        header_png=HEADERS.read(current.header_storage_name)
        if current.header_storage_name
        else None,
        key=key,
        requested_by=requested_by,
    )


def new_code() -> str:
    return base64.b32encode(secrets.token_bytes(16)).decode().rstrip("=")


def verification_url(code: str) -> str:
    return f"{django_settings.GESTCONF_PUBLIC_URL}{VERIFICATION_PATH}{code}"


def document_data(context: IssueContext, name: str, details: dict[str, Any], *, code: str, at):
    values_fr = {"name": name, **edition_values(context.edition, "fr"), **_details(details)}
    values_en = {"name": name, **edition_values(context.edition, "en"), **_details(details)}
    words = context.template.texts
    signature = context.signature
    return documents.DocumentData(
        document_title=f"{texts.fill(words['title_fr'], values_fr)} · {name}",
        edition_title=values_fr["edition"],
        title_fr=texts.fill(words["title_fr"], values_fr),
        title_en=texts.fill(words["title_en"], values_en),
        body_fr=texts.fill(words["body_fr"], values_fr),
        body_en=texts.fill(words["body_en"], values_en),
        footer_fr=texts.fill(words["footer_fr"], values_fr),
        footer_en=texts.fill(words["footer_en"], values_en),
        issued_at=at,
        timezone=context.edition.timezone,
        signatory_name=signature.display_name,
        signatory_title_fr=signature.title_fr,
        signatory_title_en=signature.title_en,
        signature_png=context.signature_png,
        header_png=context.header_png,
        verification_url=verification_url(code),
        signature_right=context.settings.layout == SignatureLayout.SIGNATURE_RIGHT,
        landscape=context.nature != DocumentNature.LETTER,
    )


def _details(details: dict[str, Any]) -> dict[str, str]:
    return {key: str(value) for key, value in details.items()}


def render_pdf(
    context: IssueContext, name: str, details: dict[str, Any], *, code: str, at
) -> bytes:
    pdf = documents.render(document_data(context, name, details, code=code, at=at))
    if context.key is not None:
        pdf = signing.sign_pdf(
            pdf,
            context.key,
            reason=str(_("Attestation délivrée par GEST-CONF")),
            location=edition_values(context.edition, "fr")["venue"] or context.edition.code,
        )
    return pdf


def issue_one(context: IssueContext, candidate: Candidate) -> Certificate | None:
    """Émet l'attestation d'une personne, sauf si elle en a déjà une active (idempotent)."""
    from apps.events import notifications

    key = candidate.active_key(context.edition, context.nature)
    if Certificate.objects.filter(active_key=key).exists():
        return None
    profile = getattr(candidate.user, "profile", None)
    name = person_name(candidate.user)
    code = new_code()
    now = timezone.now()
    pdf = render_pdf(context, name, candidate.details, code=code, at=now)
    storage_name, digest = PDFS.write(pdf)
    try:
        with transaction.atomic():
            certificate = Certificate.objects.create(
                edition=context.edition,
                user=candidate.user,
                nature=context.nature,
                submission=candidate.submission,
                name=name[:300],
                institution=(profile.institution if profile is not None else "")[:255],
                details=candidate.details,
                verification_code=code,
                storage_name=storage_name,
                sha256=digest,
                size=len(pdf),
                signing_mode=SigningMode.PADES if context.key is not None else SigningMode.IMAGE,
                signatory_name=context.signature.display_name,
                signatory_title_fr=context.signature.title_fr,
                signatory_title_en=context.signature.title_en,
                signature_sha256=context.signature.image_sha256,
                issued_at=now,
                issued_by=context.requested_by,
                active_key=key,
            )
            record(
                "certificate.issued",
                actor=SYSTEM,
                edition=context.edition,
                obj=certificate,
                after=snapshot(certificate),
            )
            notifications.certificate_available(certificate)
    except IntegrityError:
        # Émise entre-temps par une autre tâche : le fichier écrit n'est référencé par rien.
        PDFS.path(storage_name).unlink(missing_ok=True)
        return None
    return certificate


def _pending_job(edition: Edition, nature: str) -> Job | None:
    return (
        Job.objects.filter(
            kind=ISSUE_JOB,
            status__in=(JobStatus.PENDING, JobStatus.RUNNING),
            payload__edition_id=edition.pk,
            payload__nature=nature,
        )
        .order_by("id")
        .first()
    )


@transaction.atomic
def request_issuance(edition: Edition, nature: str, *, actor: Actor) -> Job:
    """Le CO lance l'émission (ou une émission complémentaire) d'une nature : conditions
    vérifiées tout de suite, travail confié à la file (``run_jobs``)."""
    preflight(edition, nature, actor.user)
    existing = _pending_job(edition, nature)
    if existing is not None:
        return existing
    job = enqueue(
        ISSUE_JOB,
        {
            "edition_id": edition.pk,
            "nature": nature,
            "requested_by": actor.user.pk if actor.user else None,
        },
    )
    record(
        "certificates.issue_requested",
        actor=actor,
        edition=edition,
        after={"nature": nature, "job": job.pk},
    )
    return job


def issue_batch(edition: Edition, nature: str, requested_by: UserType | None = None) -> int:
    """Un lot de la tâche : au plus ``ISSUE_BATCH`` attestations ; renvoie le nombre de
    personnes qui restent à traiter après ce lot."""
    context = preflight(edition, nature, requested_by)
    issued = set(
        Certificate.objects.filter(
            edition=edition, nature=nature, active_key__isnull=False
        ).values_list("active_key", flat=True)
    )
    pending = [
        candidate
        for candidate in eligibility(edition, nature).candidates
        if candidate.active_key(edition, nature) not in issued
    ]
    for candidate in pending[:ISSUE_BATCH]:
        issue_one(context, candidate)
    return max(0, len(pending) - ISSUE_BATCH)


@register_job(ISSUE_JOB)
def issue_job(job: Job) -> None:
    edition = Edition.objects.filter(pk=job.payload.get("edition_id")).first()
    if edition is None:
        return
    nature = job.payload.get("nature", "")
    requested_by = User.objects.filter(pk=job.payload.get("requested_by")).first()
    try:
        remaining = issue_batch(edition, nature, requested_by)
    except DomainError as error:
        # Conditions perdues entre la demande et l'exécution (signataire retiré, certificat
        # expiré…) : journalisé, sans nouvelle tentative ; le CO corrige et relance.
        record(
            "certificates.issue_failed",
            actor=SYSTEM,
            edition=edition,
            after={"nature": nature, "code": str(error.code)},
        )
        return
    if remaining:
        enqueue(ISSUE_JOB, dict(job.payload))


# --- Suivi, révocation, téléchargement ------------------------------------------------------------


def overview(edition: Edition) -> list[dict[str, Any]]:
    """Par nature : activée, prête (conditions de l'émission), éligibles, émises, révoquées,
    présentateurs sans compte, émission en cours."""
    rows = []
    current = certificate_settings(edition)
    for nature in CERTIFICATE_NATURES:
        enabled = nature != DocumentNature.REVIEW or current.review_enabled
        problem = ""
        if enabled:
            try:
                preflight(edition, nature)
            except DomainError as error:
                problem = str(error.code)
        found = eligibility(edition, nature) if enabled else Eligibility([], 0)
        issued = Certificate.objects.filter(edition=edition, nature=nature)
        rows.append(
            {
                "nature": nature,
                "enabled": enabled,
                "ready": enabled and not problem,
                "problem": problem,
                "eligible": len(found.candidates),
                "issued": issued.filter(revoked_at__isnull=True).count(),
                "revoked": issued.filter(revoked_at__isnull=False).count(),
                "unreachable": found.unreachable,
                "pending": _pending_job(edition, nature) is not None,
            }
        )
    return rows


@transaction.atomic
def revoke(certificate: Certificate, *, reason: str, actor: Actor) -> Certificate:
    """Révocation (RG-17) : motif obligatoire, journal ; la vérification publique répond
    « révoquée ». Rien n'est supprimé ; une nouvelle attestation peut être émise ensuite."""
    ensure_editable(certificate.edition)
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    certificate = Certificate.objects.select_for_update().get(pk=certificate.pk)
    if certificate.revoked_at is not None:
        raise RuleViolation(_("Attestation déjà révoquée."), code=ErrorCode.INVALID_TRANSITION)
    before = snapshot(certificate)
    certificate.revoked_at = timezone.now()
    certificate.revoked_by = actor.user
    certificate.revoke_reason = reason.strip()[:500]
    certificate.active_key = None
    certificate.save()
    record(
        "certificate.revoked",
        actor=actor,
        edition=certificate.edition,
        obj=certificate,
        before=before,
        after=snapshot(certificate),
        reason=reason,
    )
    return certificate


def pdf_bytes(certificate: Certificate) -> bytes:
    return PDFS.read(certificate.storage_name)


def preview(edition: Edition, nature: str) -> bytes:
    """Aperçu du gabarit (CO) : données fictives, signataire désigné s'il y en a un, jamais
    signé ni stocké."""
    if nature not in DocumentNature.values:
        raise Invalid(fields={"nature": [_("Nature inconnue.")]})
    current = certificate_settings(edition)
    template = template_for(edition, nature)
    signature = template.signatory or Signature(display_name="Signataire", title_fr="Fonction")
    context = IssueContext(
        edition=edition,
        nature=nature,
        settings=current,
        template=template,
        signature=signature,
        signature_png=signatures.image_bytes(signature) if signature.image_storage_name else None,
        header_png=HEADERS.read(current.header_storage_name)
        if current.header_storage_name
        else None,
        key=None,
        requested_by=None,
    )
    details = {
        "title": "Titre de la communication",
        "reference": f"{edition.code}-0001",
        "count": 3,
        "passport_name": "NOM Prénom",
        "nationality": "—",
        "stay": "—",
    }
    return documents.render(
        document_data(context, "Prénom Nom", details, code="A" * 26, at=timezone.now())
    )


# --- Vérification publique (K10) ------------------------------------------------------------------


def normalize_code(raw: str) -> str:
    return raw.strip().upper().replace("-", "").replace(" ", "")


def verify(raw: str) -> dict[str, Any] | None:
    """Données publiques d'une pièce : nature, nom (sauf compte anonymisé, K14), édition,
    dates, statut. Ni institution, ni empreinte. ``None`` : inconnue ou mal formée (même
    réponse, pas d'énumération)."""
    code = normalize_code(raw)
    if not CODE_PATTERN.match(code):
        return None
    certificate = (
        Certificate.objects.select_related("edition", "user").filter(verification_code=code).first()
    )
    if certificate is None:
        return None
    edition = certificate.edition
    return {
        "kind": "certificate",
        "nature": certificate.nature,
        "name": None if certificate.user.anonymized_at else certificate.name,
        "edition_title_fr": edition.title_fr,
        "edition_title_en": edition.title_en or edition.title_fr,
        "edition_start": edition.start_date,
        "edition_end": edition.end_date,
        "issued_at": certificate.issued_at,
        "status": "revoked" if certificate.revoked_at else "valid",
        "revoked_at": certificate.revoked_at,
    }


def mine(user: UserType) -> Iterable[Certificate]:
    return (
        Certificate.objects.filter(user=user)
        .select_related("edition")
        .order_by("-issued_at", "-id")
    )


def known_files() -> list[str]:
    return list(Certificate.objects.values_list("storage_name", flat=True))


def known_headers() -> list[str]:
    return list(
        CertificateSettings.objects.exclude(header_storage_name="").values_list(
            "header_storage_name", flat=True
        )
    )


def known_keys() -> list[str]:
    return list(
        CertificateSettings.objects.exclude(key_storage_name="").values_list(
            "key_storage_name", flat=True
        )
    )
