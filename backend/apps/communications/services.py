"""Mise en file et envoi des e-mails (plan L1 §8.3).

Chaîne : pendant la requête, ``queue_email`` rend le message dans la langue du
destinataire, crée une ligne ``OutboxEmail`` puis un job
``communications.send_email``, **dans la transaction métier** (une action annulée
n'envoie rien). Le cron (``run_jobs``) envoie ensuite par ``EMAIL_BACKEND``.

**Voie rapide.** Pour les seuls gabarits déclarés ``fast_path`` — des e-mails
envoyés quelle que soit l'existence d'un compte, donc sans risque d'énumération —
une tentative d'envoi immédiat est enregistrée par ``transaction.on_commit``, avec
la même réservation conditionnelle que le cron (aucun doublon). Au plus
``FAST_PATH_MAX_PER_REQUEST`` envois immédiats par requête ; les suivants partent
au cron. La réinitialisation du mot de passe n'y figure jamais : un envoi
synchrone pour une adresse connue seulement créerait un oracle temporel.

**Gabarits.** Un gabarit est déclaré par ``register_email_template`` (code =
préfixe des fichiers ``<code>_subject.txt``, ``<code>_message.txt`` et,
facultatif, ``<code>_message.html``). Le contexte est une liste blanche de
**chaînes** : jamais d'objet de l'ORM ni de requête, qu'un futur éditeur de
modèles (L3) pourrait parcourir (``{{ user.password }}``). L'objet ne contient
aucune donnée de personne : il est conservé après la purge des corps (D15).
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.db import transaction
from django.template import TemplateDoesNotExist
from django.template.loader import get_template, render_to_string
from django.utils import timezone, translation

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.core import jobs
from apps.core.models import Job, JobPriority, JobStatus

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from apps.core.actor import Actor

SEND_EMAIL_JOB = "communications.send_email"
FAST_PATH_MAX_PER_REQUEST = 3
SUBJECT_MAX_LENGTH = 255
CONTEXT_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
# Variables fournies par le service, que l'appelant ne peut pas redéfinir.
RESERVED_CONTEXT_KEYS = frozenset({"site_name"})

# D15 : corps sensibles non envoyés purgés après 24 h ; autres corps après 30 jours.
UNSENT_SENSITIVE_BODY_RETENTION = timedelta(hours=24)
BODY_RETENTION = timedelta(days=30)


# --- Registre des gabarits ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmailTemplate:
    code: str
    # Lien à jeton (vérification, réinitialisation, invitation, liaison) : corps purgé à l'envoi.
    sensitive: bool = False
    # Envoi immédiat autorisé (voir l'en-tête du module).
    fast_path: bool = False

    @property
    def priority(self) -> int:
        # Sécurité et voie rapide d'abord (plan §3.5) ; la priorité n'ordonne que le cron.
        return JobPriority.URGENT if (self.sensitive or self.fast_path) else JobPriority.NORMAL


_TEMPLATES: dict[str, EmailTemplate] = {}


def register_email_template(code: str, *, sensitive: bool = False, fast_path: bool = False) -> None:
    if len(code) > OutboxEmail._meta.get_field("template_code").max_length:
        raise ValueError(f"Code de gabarit trop long : {code}")
    template = EmailTemplate(code, sensitive=sensitive, fast_path=fast_path)
    existing = _TEMPLATES.get(code)
    if existing is not None and existing != template:
        raise ValueError(f"Gabarit déjà déclaré avec d'autres options : {code}")
    _TEMPLATES[code] = template


def email_template(code: str) -> EmailTemplate:
    try:
        return _TEMPLATES[code]
    except KeyError:
        raise ValueError(f"Gabarit d'e-mail non déclaré : {code}") from None


def registered_templates() -> list[EmailTemplate]:
    return [_TEMPLATES[code] for code in sorted(_TEMPLATES)]


def fast_path_templates() -> frozenset[str]:
    """``FAST_PATH_TEMPLATES`` du plan (§8.3) : liste blanche, sélection par gabarit."""
    return frozenset(code for code, template in _TEMPLATES.items() if template.fast_path)


# --- Plafond de la voie rapide, par requête -----------------------------------------------

# None hors requête HTTP (commandes, cron) : pas de voie rapide.
_fast_path_budget: ContextVar[int | None] = ContextVar("email_fast_path_budget", default=None)


@contextmanager
def fast_path_scope(limit: int = FAST_PATH_MAX_PER_REQUEST) -> Iterator[None]:
    """Ouvre un budget d'envois immédiats (posé par ``EmailFastPathMiddleware``)."""
    token = _fast_path_budget.set(limit)
    try:
        yield
    finally:
        _fast_path_budget.reset(token)


def _take_fast_path_slot() -> bool:
    budget = _fast_path_budget.get()
    if not budget:
        return False
    _fast_path_budget.set(budget - 1)
    return True


# --- Rendu et mise en file ------------------------------------------------------------------


def _check_context(context: Mapping[str, str]) -> dict[str, str]:
    checked: dict[str, str] = {}
    for key, value in context.items():
        if not CONTEXT_KEY_PATTERN.match(key) or key in RESERVED_CONTEXT_KEYS:
            raise ValueError(f"Variable de gabarit invalide ou réservée : {key!r}")
        if not isinstance(value, str):
            raise TypeError(
                f"Variable de gabarit {key!r} : chaîne attendue, {type(value).__name__} reçu "
                "(liste blanche, plan L1 §8.3)."
            )
        checked[key] = value
    checked["site_name"] = settings.GESTCONF_SITE_NAME
    return checked


def resolve_locale(locale: str | None, to_user: AbstractBaseUser | None) -> str:
    """Langue d'un e-mail : ``locale`` explicite, sinon celle du compte destinataire,
    sinon celle de la requête en cours ; ramenée à une langue disponible (``fr``, ``en``)."""
    candidate = locale or getattr(to_user, "locale", None) or translation.get_language()
    candidate = (candidate or settings.LANGUAGE_CODE).split("-")[0].lower()
    available = {code for code, _name in settings.LANGUAGES}
    return candidate if candidate in available else settings.LANGUAGE_CODE


def render_email(code: str, context: Mapping[str, str], locale: str) -> tuple[str, str, str]:
    """Rend (objet, texte, HTML) dans la langue demandée ; HTML vide si absent."""
    email_template(code)
    safe_context = _check_context(context)
    with translation.override(locale):
        subject = " ".join(render_to_string(f"{code}_subject.txt", safe_context).split())
        body_text = render_to_string(f"{code}_message.txt", safe_context)
        try:
            html_template = get_template(f"{code}_message.html")
        except TemplateDoesNotExist:
            body_html = ""
        else:
            body_html = html_template.render(safe_context)
    if not subject:
        raise ValueError(f"Objet vide pour le gabarit {code}")
    return subject[:SUBJECT_MAX_LENGTH], body_text, body_html


def queue_email(
    *,
    template_code: str,
    to_email: str,
    context: Mapping[str, str] | None = None,
    to_user: AbstractBaseUser | None = None,
    locale: str | None = None,
    idempotency_key: str | None = None,
    edition: Any = None,
    bulk: bool = False,
    run_at: datetime | None = None,
) -> OutboxEmail:
    """Rend et met en file un e-mail ; à appeler dans la transaction du service métier.

    Langue : ``locale`` si fournie (par exemple ``RoleInvitation.locale``), sinon
    celle du compte destinataire, sinon celle de la requête en cours.

    ``bulk`` (envoi groupé, plan L8 N11) : file ``BULK``, jamais de voie rapide, et la
    moitié du plafond horaire seulement (``send_email``) ; ``run_at`` étale l'envoi.
    """
    template = email_template(template_code)
    if idempotency_key is not None:
        existing = OutboxEmail.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing
    resolved_locale = resolve_locale(locale, to_user)
    subject, body_text, body_html = render_email(template_code, context or {}, resolved_locale)
    scheduled_at = run_at or timezone.now()
    email = OutboxEmail.objects.create(
        to_email=to_email,
        to_user=to_user,
        edition=edition,
        template_code=template_code,
        locale=resolved_locale,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        is_sensitive=template.sensitive,
        is_bulk=bulk,
        scheduled_at=scheduled_at,
        idempotency_key=idempotency_key,
    )
    job = jobs.enqueue(
        SEND_EMAIL_JOB,
        {"outbox_id": email.pk},
        run_at=scheduled_at,
        priority=JobPriority.BULK if bulk else template.priority,
        dedup_key=f"email:{email.pk}",
    )
    if template.fast_path and not bulk and _take_fast_path_slot():
        # Après la validation de la transaction (immédiatement hors transaction) ;
        # en cas d'échec, le job reste en file et le cron prend le relais.
        transaction.on_commit(partial(jobs.try_run_now, job.pk))
    return email


# --- Plafond horaire, purges, reprise -----------------------------------------------------


def hourly_limit_reached(now: datetime, *, bulk: bool = False) -> datetime | None:
    """Si le plafond horaire est atteint, date à partir de laquelle réessayer.

    Le plafond global vaut pour tous les e-mails ; un envoi groupé (``bulk``) s'arrête en
    outre à la moitié du plafond, comptée sur les seuls envois groupés de l'heure écoulée :
    l'autre moitié reste aux e-mails de compte et de service (plan L8, N11).
    """
    window_start = now - timedelta(hours=1)
    limits = [
        (
            OutboxEmail.objects.filter(sent_at__gte=window_start),
            settings.GESTCONF_EMAIL_MAX_PER_HOUR,
        )
    ]
    if bulk:
        limits.append(
            (
                OutboxEmail.objects.filter(sent_at__gte=window_start, is_bulk=True),
                bulk_hourly_limit(),
            )
        )
    for recent, limit in limits:
        if recent.count() >= limit:
            oldest = recent.order_by("sent_at").values_list("sent_at", flat=True).first()
            return (oldest or now) + timedelta(hours=1)
    return None


def bulk_hourly_limit() -> int:
    """Part du plafond horaire laissée aux envois groupés : la moitié (bilan de L8.0)."""
    return max(1, settings.GESTCONF_EMAIL_MAX_PER_HOUR // 2)


def purge_unsent_sensitive_bodies(dry_run: bool, now: datetime) -> int:
    """Sécurité (plan §3.6) : corps à jeton jamais envoyés effacés après 24 h au plus."""
    stale = OutboxEmail.objects.filter(
        is_sensitive=True,
        purged_at__isnull=True,
        created_at__lt=now - UNSENT_SENSITIVE_BODY_RETENTION,
    ).exclude(status=OutboxStatus.SENT)
    if dry_run:
        return stale.count()
    return stale.update(body_text="", body_html="", purged_at=now)


def purge_old_bodies(dry_run: bool, now: datetime) -> int:
    """D15 (non validée) : corps des e-mails traités effacés après 30 jours."""
    old = OutboxEmail.objects.filter(
        purged_at__isnull=True,
        created_at__lt=now - BODY_RETENTION,
        status__in=(OutboxStatus.SENT, OutboxStatus.FAILED, OutboxStatus.CANCELLED),
    )
    if dry_run:
        return old.count()
    return old.update(body_text="", body_html="", purged_at=now)


class EmailNotRetryable(Exception):
    """L'e-mail ne peut pas être renvoyé (déjà envoyé, ou corps sensible purgé)."""


@transaction.atomic
def retry_email(outbox_id: int, *, actor: Actor) -> OutboxEmail:
    """Remet en file un e-mail en échec (``manage.py outbox --retry``), audité."""
    from apps.core.audit import record

    email = OutboxEmail.objects.select_for_update().get(pk=outbox_id)
    if email.status != OutboxStatus.FAILED:
        raise EmailNotRetryable(f"Statut {email.status} : seul un e-mail en échec est renvoyé.")
    if email.purged_at is not None:
        raise EmailNotRetryable("Corps purgé : l'e-mail doit être redemandé par son destinataire.")
    email.status = OutboxStatus.QUEUED
    email.scheduled_at = timezone.now()
    email.save(update_fields=["status", "scheduled_at", "updated_at"])
    job = jobs.enqueue(SEND_EMAIL_JOB, {"outbox_id": email.pk}, dedup_key=f"email:{email.pk}")
    Job.objects.filter(pk=job.pk).update(
        status=JobStatus.PENDING,
        attempts=0,
        run_at=timezone.now(),
        finished_at=None,
        last_error="",
        locked_at=None,
        locked_by="",
    )
    record("email.retried", actor=actor, obj=email, after={"template": email.template_code})
    return email
