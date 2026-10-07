"""E-mails : mise en file, rendu, envoi, voie rapide (plan L1 §8.3, §4.7).

**Chaîne d'envoi.**

1. ``queue_email(...)``, appelé pendant la requête (ou par une commande), **rend** le
   message dans la langue du destinataire (``translation.override``) à partir des
   gabarits FR/EN du projet et d'un contexte en **liste blanche de chaînes** ; hors
   requête, on ne saurait plus construire les URL (§3.6).
2. Dans la transaction de l'appelant : une ligne ``OutboxEmail`` et un
   ``Job("communications.send_email", dedup_key="email:<id>")``. Une action annulée
   n'envoie rien.
3. Le gestionnaire ``send_outbox_email`` (cron ou voie rapide) ignore un e-mail déjà
   envoyé, applique le plafond horaire, passe l'e-mail en ``sending`` et **valide**
   avant d'appeler le fournisseur, puis le marque ``sent`` (corps purgé s'il est
   sensible). Un échec le remet en file ; la tâche est reprise (1 min, 5 min, 30 min, 2 h).

**Doublons.** Une panne entre l'acceptation par le fournisseur et la validation finale
peut produire un doublon, rare et assumé (§8.3) ; l'en-tête ``Message-ID``, dérivé de
l'identifiant, permet de le repérer.

**Voie rapide.** Pour les seuls gabarits de ``FAST_PATH_TEMPLATES``, une tentative
d'envoi immédiat est enregistrée par ``transaction.on_commit`` ; elle réserve la tâche
par la **même mise à jour conditionnelle** que le cron (aucun doublon possible entre les
deux), avec un délai réseau court, et au plus ``FAST_PATH_MAX_PER_REQUEST`` fois par
requête. La réinitialisation du mot de passe n'y figure jamais (oracle temporel, §8.3).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr
from functools import partial
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import EmailMultiAlternatives, get_connection
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.utils import formats, timezone, translation

from apps.communications.models import SUBJECT_MAX_LENGTH, OutboxEmail, OutboxStatus
from apps.core.jobs import (
    JobContext,
    JobDeferred,
    enqueue,
    register_job,
    run_job,
    safe_error_text,
    worker_id,
)
from apps.core.models import Job, JobStatus
from apps.core.request_context import take_fast_path_slot

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

logger = logging.getLogger(__name__)

SEND_EMAIL_JOB = "communications.send_email"
IDEMPOTENCY_KEY_MAX_LENGTH = 128

# --- Gabarits ------------------------------------------------------------------------------

# Clés de contexte admises dans les gabarits du projet (plan §8.3) : uniquement des
# chaînes. allauth passe des objets (user, request, current_site) ; un futur éditeur de
# modèles (L3) pourrait sinon afficher {{ user.password }}. Toute nouvelle clé se justifie
# en revue.
ALLOWED_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "activate_url",
        "password_reset_url",
        "signup_url",
        "site_name",
        "display_name",
        "timestamp",
        "ip",
        "user_agent",
    }
)
# Clé ajoutée par le service lui-même (nom du site, fixe).
SITE_NAME_KEY = "site_name"


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    """Gabarit d'e-mail : ``<prefix>_subject.txt``, ``<prefix>_message.txt`` et, si
    ``has_html``, ``<prefix>_message.html`` (convention d'allauth, reprise en L1.3)."""

    code: str
    prefix: str
    context_keys: frozenset[str] = frozenset()
    is_sensitive: bool = False
    has_html: bool = True

    def template_names(self) -> list[str]:
        names = [f"{self.prefix}_subject.txt", f"{self.prefix}_message.txt"]
        if self.has_html:
            names.append(f"{self.prefix}_message.html")
        return names


EMAIL_TEMPLATES: dict[str, EmailTemplate] = {}


def register_template(template: EmailTemplate) -> EmailTemplate:
    unknown = template.context_keys - ALLOWED_CONTEXT_KEYS
    if unknown:
        raise ImproperlyConfigured(f"Clés de contexte hors liste blanche : {sorted(unknown)}")
    existing = EMAIL_TEMPLATES.get(template.code)
    if existing is not None and existing != template:
        raise ImproperlyConfigured(f"Gabarit d'e-mail déjà enregistré : {template.code}")
    EMAIL_TEMPLATES[template.code] = template
    return template


# E-mail de test de l'opérateur (send_test_email, jalon J-tech).
TEST_EMAIL = register_template(
    EmailTemplate(
        code="communications.test_email",
        prefix="communications/email/test_email",
        context_keys=frozenset({"timestamp"}),
    )
)

# Voie rapide (plan §8.3) : sélection par gabarit, pas par priorité. Seulement des e-mails
# envoyés quelle que soit l'existence d'un compte (aucun oracle d'énumération). Ces gabarits
# seront créés en L1.3 (comptes), L1.5 (invitations) et L1.6 (2FA) ; les codes suivent la
# convention « application.nom » des préfixes d'allauth (« account/email/<nom> »).
FAST_PATH_TEMPLATES: frozenset[str] = frozenset(
    {
        # Inscription : l'un ou l'autre part dans tous les cas.
        "account.email_confirmation_signup",
        "account.account_already_exists",
        # Vérification d'adresse renvoyée à la reconnexion (identifiants exacts exigés).
        "account.email_confirmation",
        # Invitations, envoyées par un membre authentifié (plafond par requête).
        "role.invitation",
        # Liaison d'une adresse invitée (RG-20, option (a) de D6).
        "role.invitation_link",
        # Notifications de sécurité d'un utilisateur connecté, dont « adresse ajoutée ».
        "account.email_added",
        "account.email_changed",
        "account.email_deleted",
        "account.password_changed",
        "account.password_set",
        "mfa.totp_activated",
        "mfa.totp_deactivated",
        "mfa.recovery_codes_generated",
    }
)
# Jamais en voie rapide : la réinitialisation du mot de passe (un envoi synchrone pour une
# adresse connue, absent pour une inconnue, serait un oracle temporel, §8.3, R20).
NEVER_FAST_PATH_TEMPLATES: frozenset[str] = frozenset(
    {"account.password_reset_key", "account.unknown_account"}
)
if FAST_PATH_TEMPLATES & NEVER_FAST_PATH_TEMPLATES:  # pragma: no cover (garde de revue)
    raise ImproperlyConfigured(
        "La réinitialisation du mot de passe ne prend jamais la voie rapide."
    )


def resolve_locale(locale: str | None = None, to_user: AbstractBaseUser | None = None) -> str:
    """Langue du message : explicite, sinon celle du compte, sinon celle de la requête.

    Toujours ramenée à une langue de ``LANGUAGES`` (``fr`` par défaut).
    """
    candidate = locale or getattr(to_user, "locale", "") or translation.get_language() or ""
    try:
        return translation.get_supported_language_variant(candidate)
    except LookupError:
        return settings.LANGUAGE_CODE


def format_timestamp(value: datetime, locale: str) -> str:
    """Date et heure UTC formatées dans la langue du destinataire (contexte des gabarits)."""
    with translation.override(locale):
        return f"{formats.date_format(value.astimezone(UTC), 'DATETIME_FORMAT')} UTC"


def _template_context(template: EmailTemplate, context: Mapping[str, str] | None) -> dict[str, str]:
    context = dict(context or {})
    unknown = set(context) - template.context_keys
    if unknown:
        raise ValueError(f"Clés de contexte non déclarées par {template.code} : {sorted(unknown)}")
    not_strings = sorted(key for key, value in context.items() if not isinstance(value, str))
    if not_strings:
        raise TypeError(f"Le contexte d'un e-mail ne contient que des chaînes : {not_strings}")
    return {SITE_NAME_KEY: settings.GESTCONF_SITE_NAME, **context}


def render_email(
    template: EmailTemplate, context: Mapping[str, str], locale: str
) -> tuple[str, str, str]:
    """(objet, texte, HTML) rendus dans ``locale`` ; objet sur une ligne, 255 caractères."""
    with translation.override(locale):
        subject = render_to_string(f"{template.prefix}_subject.txt", context)
        body_text = render_to_string(f"{template.prefix}_message.txt", context)
        body_html = (
            render_to_string(f"{template.prefix}_message.html", context)
            if template.has_html
            else ""
        )
    subject = " ".join(subject.split())[:SUBJECT_MAX_LENGTH]
    return subject, body_text, body_html


def queue_email(
    template_code: str,
    *,
    to_email: str,
    context: Mapping[str, str] | None = None,
    to_user: AbstractBaseUser | None = None,
    locale: str | None = None,
    idempotency_key: str | None = None,
    scheduled_at: datetime | None = None,
) -> OutboxEmail:
    """Rend un e-mail et le met en file dans la transaction de l'appelant.

    Renvoie la ligne ``OutboxEmail`` (existante si ``idempotency_key`` a déjà servi).
    """
    template = EMAIL_TEMPLATES.get(template_code)
    if template is None:
        raise ValueError(f"Gabarit d'e-mail inconnu : {template_code!r}")
    to_email = to_email.strip()
    validate_email(to_email)
    if idempotency_key is not None and not 0 < len(idempotency_key) <= IDEMPOTENCY_KEY_MAX_LENGTH:
        raise ValueError("Clé d'idempotence : 1 à 128 caractères.")
    full_context = _template_context(template, context)
    language = resolve_locale(locale, to_user)
    subject, body_text, body_html = render_email(template, full_context, language)
    fast_path = template_code in FAST_PATH_TEMPLATES
    now = timezone.now()
    run_at = scheduled_at or now

    with transaction.atomic():
        if idempotency_key is not None:
            existing = OutboxEmail.objects.filter(idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing
        try:
            with transaction.atomic():
                email = OutboxEmail.objects.create(
                    to_email=to_email,
                    to_user=to_user,
                    template_code=template_code,
                    locale=language,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    is_sensitive=template.is_sensitive,
                    scheduled_at=run_at,
                    idempotency_key=idempotency_key,
                )
        except IntegrityError:
            if idempotency_key is None:
                raise
            return OutboxEmail.objects.get(idempotency_key=idempotency_key)
        job = enqueue(
            SEND_EMAIL_JOB,
            {"outbox_id": email.pk},
            run_at=run_at,
            priority=Job.PRIORITY_URGENT if fast_path else Job.PRIORITY_DEFAULT,
            dedup_key=f"email:{email.pk}",
        )
        if fast_path and run_at <= now and take_fast_path_slot():
            transaction.on_commit(partial(_send_now, job.pk), robust=True)
    return email


def _send_now(job_id: int) -> None:
    """Voie rapide : même réservation conditionnelle que le cron ; un échec lui laisse la main."""
    try:
        run_job(job_id, worker=worker_id(), fast_path=True)
    except Exception:
        logger.exception(
            "Voie rapide : échec inattendu (tâche %s) ; le cron prendra le relais.", job_id
        )


# --- Envoi ---------------------------------------------------------------------------------


def message_id(email: OutboxEmail) -> str:
    """En-tête ``Message-ID`` dérivé de l'identifiant (et de la date de création, pour rester
    unique si la base est un jour recréée) : un doublon garde le même identifiant."""
    domain = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2] or "localhost"
    return f"<gestconf.{email.pk}.{int(email.created_at.timestamp())}@{domain}>"


def hourly_cap_release(now: datetime) -> datetime | None:
    """Plafond global d'envoi (§4.7) : ``None`` sous le plafond, sinon l'instant où il se libère.

    Plafond « souple » : deux envoyeurs simultanés (cron et voie rapide) peuvent le
    dépasser de quelques unités ; il protège la réputation du domaine, pas un quota strict.
    """
    cap = settings.GESTCONF_EMAIL_MAX_PER_HOUR
    window = timedelta(hours=1)
    recent = OutboxEmail.objects.filter(sent_at__gte=now - window)
    count = recent.count()
    if count < cap:
        return None
    # Il faut que (count - cap + 1) envois sortent de la fenêtre glissante.
    oldest = recent.order_by("sent_at").values_list("sent_at", flat=True)[count - cap]
    return oldest + window + timedelta(seconds=1)


def _build_message(email: OutboxEmail, *, timeout: float | None) -> EmailMultiAlternatives:
    connection = get_connection() if timeout is None else get_connection(timeout=timeout)
    message = EmailMultiAlternatives(
        subject=email.subject,
        body=email.body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email.to_email],
        headers={"Message-ID": message_id(email)},
        connection=connection,
    )
    if email.body_html:
        message.attach_alternative(email.body_html, "text/html")
    return message


def _provider_message_id(message: EmailMultiAlternatives) -> str:
    """Identifiant attribué par le fournisseur (anymail), s'il y en a un."""
    status = getattr(message, "anymail_status", None)
    value = getattr(status, "message_id", None)
    if isinstance(value, set):
        value = ",".join(sorted(str(item) for item in value))
    return str(value)[:255] if value else ""


def _mark_failed(payload: dict[str, Any]) -> None:
    """Échec définitif de la tâche : l'e-mail passe en ``failed`` (sauf s'il est parti)."""
    OutboxEmail.objects.filter(pk=payload.get("outbox_id")).exclude(
        status__in=[OutboxStatus.SENT, OutboxStatus.CANCELLED]
    ).update(status=OutboxStatus.FAILED, updated_at=timezone.now())


@register_job(SEND_EMAIL_JOB, on_final_failure=_mark_failed)
def send_outbox_email(payload: dict[str, Any], context: JobContext) -> None:
    """Envoie un ``OutboxEmail`` ; idempotent (un e-mail ``sent`` n'est jamais renvoyé)."""
    outbox_id = payload["outbox_id"]
    current = OutboxEmail.objects.filter(pk=outbox_id).values_list("status", "purged_at").first()
    if current is None:
        logger.warning("E-mail %s introuvable (purgé ?) : rien à envoyer.", outbox_id)
        return
    status, purged_at = current
    if status in (OutboxStatus.SENT, OutboxStatus.CANCELLED):
        return
    if purged_at is not None:
        # Corps sensible purgé après 24 h sans envoi : le lien n'est plus disponible.
        OutboxEmail.objects.filter(pk=outbox_id).exclude(status=OutboxStatus.SENT).update(
            status=OutboxStatus.CANCELLED, updated_at=timezone.now()
        )
        return

    now = timezone.now()
    release = hourly_cap_release(now)
    if release is not None:
        OutboxEmail.objects.filter(pk=outbox_id).update(scheduled_at=release, updated_at=now)
        raise JobDeferred(release, "plafond horaire d'envoi atteint")

    # « sending » validé AVANT l'appel au fournisseur (plan §8.3).
    with transaction.atomic():
        email = OutboxEmail.objects.select_for_update().get(pk=outbox_id)
        if email.status in (OutboxStatus.SENT, OutboxStatus.CANCELLED):
            return
        email.status = OutboxStatus.SENDING
        email.attempts += 1
        email.save(update_fields=["status", "attempts", "updated_at"])

    timeout = settings.GESTCONF_EMAIL_FAST_PATH_TIMEOUT if context.fast_path else None
    message = _build_message(email, timeout=timeout)
    try:
        if message.send() != 1:
            raise RuntimeError("Le backend d'e-mail n'a rien envoyé.")
    except Exception as exc:
        OutboxEmail.objects.filter(pk=outbox_id, status=OutboxStatus.SENDING).update(
            status=OutboxStatus.QUEUED, last_error=safe_error_text(exc), updated_at=timezone.now()
        )
        raise

    sent_at = timezone.now()
    fields: dict[str, Any] = {
        "status": OutboxStatus.SENT,
        "sent_at": sent_at,
        "provider_message_id": _provider_message_id(message),
        "last_error": "",
        "updated_at": sent_at,
    }
    if email.is_sensitive:
        fields.update(body_text="", body_html="", purged_at=sent_at)
    OutboxEmail.objects.filter(pk=outbox_id).update(**fields)


def retry_failed_email(email: OutboxEmail) -> OutboxEmail:
    """Remet en file un e-mail en échec (commande ``outbox --retry``), dans la transaction
    de l'appelant ; la tâche associée repart de zéro tentative."""
    if email.status != OutboxStatus.FAILED:
        raise ValueError("Seul un e-mail en échec peut être renvoyé.")
    if email.purged_at is not None:
        raise ValueError("Corps purgé : cet e-mail ne peut plus être renvoyé.")
    now = timezone.now()
    email.status = OutboxStatus.QUEUED
    email.scheduled_at = now
    email.save(update_fields=["status", "scheduled_at", "updated_at"])
    job = enqueue(
        SEND_EMAIL_JOB, {"outbox_id": email.pk}, run_at=now, dedup_key=f"email:{email.pk}"
    )
    Job.objects.filter(pk=job.pk).exclude(status=JobStatus.RUNNING).update(
        status=JobStatus.PENDING,
        attempts=0,
        run_at=now,
        finished_at=None,
        locked_at=None,
        locked_by="",
        updated_at=now,
    )
    return email
