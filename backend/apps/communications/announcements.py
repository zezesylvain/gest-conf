"""Annonces et envois groupés (plan L8, N10 et N11 ; RG-22 proposée).

Une annonce porte un titre et un texte FR et EN (HTML en liste blanche, assaini par
l'assainisseur de L2) et des **canaux** :

- **actualités** du portail, pré-rendues : visibles après ``deploy.sh --portal-only`` (les
  modifications d'une actualité publiée comptent dans les modifications non publiées) ;
- **bandeau** de dernière minute : texte seul (280 caractères), visible **aussitôt** entre
  un début et une fin saisis en heure locale de l'édition (D13) ; une seule annonce au
  bandeau à la fois (fenêtres disjointes) ;
- **cloche** et **e-mail** : aux destinataires d'un **segment** (``segments.py``).

**RG-22** : un envoi groupé ne part qu'à la publication, après réauthentification (vue),
vers un segment du catalogue fermé dont les destinataires sont comptés ; un e-mail par
personne, jamais de liste en copie, dans la langue du compte, avec la raison de l'envoi et
un lien de désabonnement des annonces (les e-mails de service restent envoyés) ; la mise en
file se fait par lots (job ``communications.fan_out``), les e-mails sont étalés et n'usent
que **la moitié** du plafond horaire ; ce qui n'est pas parti peut être annulé ; tout est
journalisé (RG-17).
"""

from __future__ import annotations

import datetime as dt
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Count, QuerySet
from django.utils import timezone, translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.services.roles import ensure_editable
from apps.communications.models import (
    Announcement,
    AnnouncementDelivery,
    AnnouncementOptOut,
    AnnouncementStatus,
    NotificationKind,
    OutboxEmail,
    OutboxStatus,
    SendingStatus,
)
from apps.communications.notifications import notify
from apps.communications.segments import Segment, get_segment, recipients
from apps.communications.services import bulk_hourly_limit, queue_email, resolve_locale
from apps.communications.text import absolute_href, html_to_text
from apps.conferences.models import Edition
from apps.conferences.services import local_to_utc
from apps.core import jobs
from apps.core.actor import Actor
from apps.core.audit import mask_emails, record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import Job, JobPriority

TEMPLATE = "communications/email/announcement"
FAN_OUT_JOB = "communications.fan_out"
FAN_OUT_BATCH = 200
UNSUBSCRIBE_SALT = "gestconf.announcements.unsubscribe"
UNSUBSCRIBE_PATH = "/desabonnement/"
TITLE_LIMIT = 150
BANNER_LIMIT = 280
BODY_LIMIT = 20_000

TEXT_FIELDS = ("title_fr", "title_en", "banner_message_fr", "banner_message_en")
BODY_FIELDS = ("body_fr", "body_en")
CHANNEL_FIELDS = ("on_news", "on_banner", "on_bell", "by_email")
LOCAL_FIELDS = {"banner_starts_local": "banner_starts_at", "banner_ends_local": "banner_ends_at"}
FIELDS = frozenset((*TEXT_FIELDS, *BODY_FIELDS, *CHANNEL_FIELDS, "segment", *LOCAL_FIELDS))
# Une fois publiée, l'annonce garde ses destinataires : la cloche, l'e-mail et le segment ne
# changent plus (l'envoi est parti) ; le reste se corrige.
LOCKED_AFTER_PUBLICATION = frozenset({"on_bell", "by_email", "segment"})
# Champs dont la modification change le portail pré-rendu (actualités).
NEWS_FIELDS = frozenset({"title_fr", "title_en", "body_fr", "body_en", "on_news"})

_HREF = re.compile(r'href="(/[^/"][^"]*|/)"')


# --- Saisie ------------------------------------------------------------------------------


def _clean(
    edition: Edition,
    data: Mapping[str, Any],
    *,
    capabilities: Iterable[str],
    creating: bool,
) -> dict[str, Any]:
    from apps.portal.sanitizer import sanitize_html

    unknown = set(data) - FIELDS
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    limits = {
        "title_fr": TITLE_LIMIT,
        "title_en": TITLE_LIMIT,
        "banner_message_fr": BANNER_LIMIT,
        "banner_message_en": BANNER_LIMIT,
    }
    for name, limit in limits.items():
        if name in data:
            value = " ".join((data[name] or "").split())
            if len(value) > limit:
                errors[name] = [_("%(limit)s caractères au plus.") % {"limit": limit}]
            clean[name] = value
    if (creating or "title_fr" in clean) and not clean.get("title_fr"):
        errors["title_fr"] = [_("Titre obligatoire.")]
    for name in BODY_FIELDS:
        if name in data:
            raw = data[name] or ""
            if len(raw) > BODY_LIMIT:
                errors[name] = [_("Texte trop long.")]
            else:
                clean[name] = sanitize_html(raw)
    for name in CHANNEL_FIELDS:
        if name in data:
            clean[name] = bool(data[name])
    if "segment" in data:
        code = (data["segment"] or "").strip()
        if code:
            get_segment(code, capabilities)  # inconnu ou réservé : erreur
        clean["segment"] = code
    for local, field in LOCAL_FIELDS.items():
        if local in data:
            value = data[local]
            if value is None:
                clean[field] = None
            elif not isinstance(value, dt.datetime):
                errors[local] = [_("Date et heure attendues.")]
            else:
                try:
                    clean[field] = local_to_utc(value, edition.timezone)
                except Invalid as error:
                    errors[local] = list(error.fields.get("at_local", [error.message]))
    if errors:
        raise Invalid(fields=errors)
    return clean


def _snapshot(announcement: Announcement) -> dict[str, Any]:
    return mask_emails(
        {
            "title_fr": announcement.title_fr,
            "title_en": announcement.title_en,
            "on_news": announcement.on_news,
            "on_banner": announcement.on_banner,
            "on_bell": announcement.on_bell,
            "by_email": announcement.by_email,
            "segment": announcement.segment,
            "banner_starts_at": _iso(announcement.banner_starts_at),
            "banner_ends_at": _iso(announcement.banner_ends_at),
        }
    )


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def _banner_overlaps(announcement: Announcement) -> bool:
    return (
        Announcement.objects.filter(
            edition_id=announcement.edition_id,
            status=AnnouncementStatus.PUBLISHED,
            on_banner=True,
            banner_starts_at__lt=announcement.banner_ends_at,
            banner_ends_at__gt=announcement.banner_starts_at,
        )
        .exclude(pk=announcement.pk)
        .exists()
    )


def _check_banner(announcement: Announcement) -> None:
    if not announcement.on_banner:
        return
    errors: dict[str, list] = {}
    if not announcement.banner_message_fr:
        errors["banner_message_fr"] = [_("Message du bandeau obligatoire.")]
    if not announcement.banner_starts_at:
        errors["banner_starts_local"] = [_("Début du bandeau obligatoire.")]
    if not announcement.banner_ends_at:
        errors["banner_ends_local"] = [_("Fin du bandeau obligatoire.")]
    elif announcement.banner_starts_at and (
        announcement.banner_ends_at <= announcement.banner_starts_at
    ):
        errors["banner_ends_local"] = [_("Fin après le début.")]
    if errors:
        raise Invalid(fields=errors)
    if announcement.status == AnnouncementStatus.PUBLISHED and _banner_overlaps(announcement):
        raise RuleViolation(
            _("Une autre annonce occupe déjà le bandeau sur cette période."),
            code=ErrorCode.BANNER_OVERLAP,
        )


def _check_publishable(announcement: Announcement) -> None:
    errors: dict[str, list] = {}
    if not any(getattr(announcement, name) for name in CHANNEL_FIELDS):
        errors["channels"] = [_("Choisissez au moins un canal.")]
    if (announcement.on_news or announcement.by_email) and not announcement.body_fr:
        errors["body_fr"] = [_("Texte obligatoire pour les actualités et l'e-mail.")]
    if (announcement.on_bell or announcement.by_email) and not announcement.segment:
        errors["segment"] = [_("Segment obligatoire pour la cloche et l'e-mail.")]
    if errors:
        raise Invalid(fields=errors)
    _check_banner(announcement)


# --- Écritures ---------------------------------------------------------------------------


@transaction.atomic
def create_announcement(
    edition: Edition, data: Mapping[str, Any], *, capabilities: Iterable[str], actor: Actor
) -> Announcement:
    ensure_editable(edition)
    clean = _clean(edition, data, capabilities=capabilities, creating=True)
    announcement = Announcement(edition=edition, created_by=actor.user, **clean)
    _check_banner(announcement)
    announcement.save()
    record(
        "announcement.created",
        actor=actor,
        edition=edition,
        obj=announcement,
        after=_snapshot(announcement),
    )
    return announcement


def _locked(announcement_id: int) -> Announcement:
    return (
        Announcement.objects.select_for_update().select_related("edition").get(pk=announcement_id)
    )


@transaction.atomic
def update_announcement(
    announcement: Announcement,
    data: Mapping[str, Any],
    *,
    capabilities: Iterable[str],
    actor: Actor,
) -> Announcement:
    ensure_editable(announcement.edition)
    announcement = _locked(announcement.pk)
    if announcement.status == AnnouncementStatus.WITHDRAWN:
        raise RuleViolation(_("Annonce retirée."), code=ErrorCode.INVALID_TRANSITION)
    clean = _clean(announcement.edition, data, capabilities=capabilities, creating=False)
    published = announcement.status == AnnouncementStatus.PUBLISHED
    if published:
        locked = sorted(
            name
            for name in LOCKED_AFTER_PUBLICATION
            if name in clean and clean[name] != getattr(announcement, name)
        )
        if locked:
            raise Invalid(fields={name: [_("Déjà envoyée : non modifiable.")] for name in locked})
    before = _snapshot(announcement)
    was_news = announcement.on_news
    changed = [name for name, value in clean.items() if getattr(announcement, name) != value]
    for name, value in clean.items():
        setattr(announcement, name, value)
    if published:
        _check_publishable(announcement)
    else:
        _check_banner(announcement)
    announcement.save()
    if changed:
        after = _snapshot(announcement)
        # Une actualité publiée modifiée change le portail pré-rendu.
        public = (
            published and (was_news or announcement.on_news) and bool(NEWS_FIELDS & set(changed))
        )
        record(
            "announcement.updated",
            actor=actor,
            edition=announcement.edition,
            obj=announcement,
            before={name: before[name] for name in after if before[name] != after[name]},
            after={
                **{name: after[name] for name in after if before[name] != after[name]},
                "fields": sorted(changed),
                "public": public,
            },
        )
    return announcement


@transaction.atomic
def delete_announcement(announcement: Announcement, *, actor: Actor) -> None:
    ensure_editable(announcement.edition)
    announcement = _locked(announcement.pk)
    if announcement.status != AnnouncementStatus.DRAFT:
        raise RuleViolation(
            _("Seul un brouillon se supprime ; une annonce publiée se retire."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    record(
        "announcement.deleted",
        actor=actor,
        edition=announcement.edition,
        obj=announcement,
        before=_snapshot(announcement),
    )
    announcement.delete()


@transaction.atomic
def publish(
    announcement: Announcement, *, capabilities: Iterable[str], actor: Actor
) -> Announcement:
    """Publie : actualité (au prochain ``--portal-only``), bandeau (aussitôt), cloche et
    e-mail (mise en file par lots). La réauthentification est vérifiée par la vue."""
    ensure_editable(announcement.edition)
    announcement = _locked(announcement.pk)
    if announcement.status != AnnouncementStatus.DRAFT:
        raise RuleViolation(
            _("Annonce déjà publiée ou retirée."), code=ErrorCode.INVALID_TRANSITION
        )
    if announcement.segment:
        # Le segment est revérifié avec les capacités de qui publie (RG-22).
        get_segment(announcement.segment, capabilities)
    now = timezone.now()
    announcement.status = AnnouncementStatus.PUBLISHED
    announcement.published_at = now
    _check_publishable(announcement)
    sending = announcement.on_bell or announcement.by_email
    if sending:
        segment = _segment(announcement)
        announcement.recipients_count = recipients(announcement.edition, segment).count()
        announcement.sending_status = SendingStatus.QUEUING
        announcement.sending_started_at = now
    announcement.save()
    record(
        "announcement.published",
        actor=actor,
        edition=announcement.edition,
        obj=announcement,
        after={**_snapshot(announcement), "public": announcement.on_news},
    )
    if sending:
        # Action de masse (RG-17) : segment et nombre de destinataires au journal.
        record(
            "announcement.sent",
            actor=actor,
            edition=announcement.edition,
            obj=announcement,
            after={
                "segment": announcement.segment,
                "recipients": announcement.recipients_count,
                "bell": announcement.on_bell,
                "email": announcement.by_email,
            },
        )
        _enqueue_fan_out(announcement)
    return announcement


@transaction.atomic
def withdraw(announcement: Announcement, *, actor: Actor) -> Announcement:
    """Retire des actualités et du bandeau ; annule les e-mails pas encore partis."""
    ensure_editable(announcement.edition)
    announcement = _locked(announcement.pk)
    if announcement.status != AnnouncementStatus.PUBLISHED:
        raise RuleViolation(
            _("Seule une annonce publiée se retire."), code=ErrorCode.INVALID_TRANSITION
        )
    cancelled = _cancel_sending(announcement) if _sending(announcement) else 0
    announcement.status = AnnouncementStatus.WITHDRAWN
    announcement.withdrawn_at = timezone.now()
    announcement.save()
    record(
        "announcement.withdrawn",
        actor=actor,
        edition=announcement.edition,
        obj=announcement,
        after={"public": announcement.on_news, "cancelled": cancelled},
    )
    return announcement


@transaction.atomic
def cancel_sending(announcement: Announcement, *, actor: Actor) -> int:
    """Annule ce qui n'est pas encore parti (mise en file arrêtée, e-mails en file annulés)."""
    ensure_editable(announcement.edition)
    announcement = _locked(announcement.pk)
    if not _sending(announcement):
        raise RuleViolation(_("Aucun envoi en cours."), code=ErrorCode.INVALID_TRANSITION)
    cancelled = _cancel_sending(announcement)
    announcement.save()
    record(
        "announcement.sending_cancelled",
        actor=actor,
        edition=announcement.edition,
        obj=announcement,
        after={"cancelled": cancelled},
    )
    return cancelled


def _sending(announcement: Announcement) -> bool:
    return announcement.sending_status in (SendingStatus.QUEUING, SendingStatus.QUEUED)


def _cancel_sending(announcement: Announcement) -> int:
    announcement.sending_status = SendingStatus.CANCELLED
    announcement.sending_finished_at = timezone.now()
    return (
        _emails(announcement)
        .filter(status=OutboxStatus.QUEUED)
        .update(status=OutboxStatus.CANCELLED)
    )


# --- Destinataires et mise en file -------------------------------------------------------


def _segment(announcement: Announcement) -> Segment:
    """Segment de l'annonce ; sa capacité a été vérifiée à l'enregistrement et à la
    publication."""
    from apps.communications.segments import _SEGMENTS

    segment = _SEGMENTS.get(announcement.segment)
    if segment is None:
        raise Invalid(fields={"segment": [_("Segment inconnu.")]})
    return segment


def email_key(announcement: Announcement, user_id: int) -> str:
    return f"announcement:{announcement.pk}:{user_id}"


def _emails(announcement: Announcement) -> QuerySet[OutboxEmail]:
    return OutboxEmail.objects.filter(
        idempotency_key__startswith=f"announcement:{announcement.pk}:"
    )


def bulk_per_hour() -> int:
    return bulk_hourly_limit()


def estimated_hours(emails: int) -> int:
    return math.ceil(emails / bulk_per_hour()) if emails else 0


def _enqueue_fan_out(announcement: Announcement) -> Job:
    return jobs.enqueue(
        FAN_OUT_JOB,
        {"announcement_id": announcement.pk},
        priority=JobPriority.BULK,
        dedup_key=f"announcement:{announcement.pk}:fan_out:{announcement.fan_out_cursor}",
    )


def _pick(announcement: Announcement, name: str, locale: str) -> str:
    english = getattr(announcement, f"{name}_en")
    return english if locale == "en" and english else getattr(announcement, f"{name}_fr")


def unsubscribe_token(user: User, edition: Edition) -> str:
    return signing.dumps({"u": user.pk, "e": edition.pk}, salt=UNSUBSCRIBE_SALT)


def unsubscribe_url(user: User, edition: Edition) -> str:
    return f"{settings.GESTCONF_PUBLIC_URL}{UNSUBSCRIBE_PATH}{unsubscribe_token(user, edition)}"


def email_context(
    announcement: Announcement, user: User, locale: str, *, test: bool = False
) -> dict[str, str]:
    """Contexte du gabarit, en chaînes (liste blanche des gabarits, plan L1 §8.3)."""
    base = settings.GESTCONF_PUBLIC_URL
    body = _pick(announcement, "body", locale)
    body_html = _HREF.sub(lambda match: f'href="{absolute_href(match.group(1), base)}"', body)
    edition = announcement.edition
    with translation.override(locale):
        reason = gettext(
            "Vous recevez ce message au titre de « %(segment)s » pour %(edition)s."
        ) % {
            "segment": str(_segment(announcement).label),
            "edition": edition.title_en
            if locale == "en" and edition.title_en
            else edition.title_fr,
        }
        notice = gettext("Essai : ce message n'a été envoyé qu'à vous.") if test else ""
    return {
        "title": _pick(announcement, "title", locale),
        "body_html": body_html,
        "body_text": html_to_text(body, base_url=base),
        "reason": reason,
        "unsubscribe_url": unsubscribe_url(user, edition),
        "test_notice": notice,
        "language": locale,
    }


def _queue(announcement: Announcement, user: User, *, run_at: dt.datetime) -> OutboxEmail:
    locale = resolve_locale(None, user)
    return queue_email(
        template_code=TEMPLATE,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=email_context(announcement, user, locale),
        idempotency_key=email_key(announcement, user.pk),
        edition=announcement.edition,
        bulk=True,
        run_at=run_at,
    )


def fan_out_batch(announcement_id: int, *, now: dt.datetime | None = None) -> bool:
    """Un lot de la mise en file ; ``True`` s'il en reste. Idempotent : une livraison
    existante n'est ni renotifiée ni réenvoyée."""
    now = now or timezone.now()
    with transaction.atomic():
        announcement = (
            Announcement.objects.select_for_update()
            .select_related("edition")
            .filter(pk=announcement_id)
            .first()
        )
        if announcement is None or announcement.sending_status != SendingStatus.QUEUING:
            return False
        segment = _segment(announcement)
        batch = list(
            recipients(announcement.edition, segment).filter(pk__gt=announcement.fan_out_cursor)[
                :FAN_OUT_BATCH
            ]
        )
        opted_out = set(
            AnnouncementOptOut.objects.filter(
                edition=announcement.edition, user__in=batch
            ).values_list("user_id", flat=True)
        )
        done = set(
            AnnouncementDelivery.objects.filter(
                announcement=announcement, user__in=batch
            ).values_list("user_id", flat=True)
        )
        per_hour = bulk_per_hour()
        start = announcement.sending_started_at or now
        payload = {
            "edition_id": announcement.edition_id,
            "edition_code": announcement.edition.code,
            "announcement_id": announcement.pk,
            "title_fr": announcement.title_fr,
            "title_en": announcement.title_en,
        }
        for user in batch:
            if user.pk in done:
                continue
            emailed = announcement.by_email and user.pk not in opted_out
            AnnouncementDelivery.objects.create(
                announcement=announcement, user=user, emailed=emailed
            )
            if announcement.on_bell:
                notify(user, NotificationKind.ANNOUNCEMENT, payload)
            if emailed:
                # Étalement : un lot égal à la moitié du plafond par heure (bilan de L8.0).
                slot = start + dt.timedelta(hours=announcement.emails_count // per_hour)
                _queue(announcement, user, run_at=max(slot, now))
                announcement.emails_count += 1
            announcement.delivered_count += 1
        if batch:
            announcement.fan_out_cursor = batch[-1].pk
        more = len(batch) == FAN_OUT_BATCH
        if not more:
            announcement.sending_status = SendingStatus.QUEUED
        announcement.save()
        if more:
            _enqueue_fan_out(announcement)
    return more


def sending_stats(announcement: Announcement) -> dict[str, int]:
    """Avancement de l'envoi : e-mails par statut, livraisons, durée estimée."""
    by_status = dict(
        _emails(announcement)
        .values_list("status")
        .annotate(n=Count("id"))
        .values_list("status", "n")
    )
    queued = by_status.get(OutboxStatus.QUEUED, 0) + by_status.get(OutboxStatus.SENDING, 0)
    return {
        "recipients": announcement.recipients_count,
        "delivered": announcement.delivered_count,
        "emails": announcement.emails_count,
        "sent": by_status.get(OutboxStatus.SENT, 0),
        "queued": queued,
        "failed": by_status.get(OutboxStatus.FAILED, 0),
        "cancelled": by_status.get(OutboxStatus.CANCELLED, 0),
        "remaining_hours": estimated_hours(queued),
    }


# --- Aperçu et essai ---------------------------------------------------------------------


def audience(announcement: Announcement) -> dict[str, int]:
    """Destinataires comptés avant l'envoi : comptes, désabonnés, e-mails, durée estimée."""
    if not announcement.segment:
        return {"recipients": 0, "opted_out": 0, "emails": 0, "estimated_hours": 0}
    people = recipients(announcement.edition, _segment(announcement))
    total = people.count()
    opted_out = AnnouncementOptOut.objects.filter(
        edition=announcement.edition, user__in=people.values("pk")
    ).count()
    emails = total - opted_out if announcement.by_email else 0
    return {
        "recipients": total,
        "opted_out": opted_out,
        "emails": emails,
        "estimated_hours": estimated_hours(emails),
    }


def preview(announcement: Announcement, user: User, locale: str) -> dict[str, Any]:
    from apps.communications.services import render_email

    context = email_context(announcement, user, locale)
    subject, body_text, body_html = render_email(TEMPLATE, context, locale)
    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
        **audience(announcement),
    }


@transaction.atomic
def send_test(announcement: Announcement, *, actor: Actor) -> OutboxEmail:
    """Essai : le message, tel qu'il partira, à la seule personne qui le demande."""
    ensure_editable(announcement.edition)
    if not announcement.segment or not announcement.body_fr:
        raise Invalid(fields={"segment": [_("Segment et texte nécessaires à l'essai.")]})
    user = actor.user
    locale = resolve_locale(None, user)
    email = queue_email(
        template_code=TEMPLATE,
        to_email=user.email,
        to_user=user,
        locale=locale,
        context=email_context(announcement, user, locale, test=True),
        edition=announcement.edition,
    )
    record("announcement.tested", actor=actor, edition=announcement.edition, obj=announcement)
    return email


# --- Désabonnement -----------------------------------------------------------------------


def _read_token(token: str) -> tuple[User, Edition]:
    try:
        data = signing.loads(token, salt=UNSUBSCRIBE_SALT)
        user = User.objects.get(pk=int(data["u"]), is_active=True, anonymized_at__isnull=True)
        edition = Edition.objects.get(pk=int(data["e"]))
    except (
        signing.BadSignature,
        KeyError,
        TypeError,
        ValueError,
        User.DoesNotExist,
        Edition.DoesNotExist,
    ):
        raise Invalid(
            code=ErrorCode.UNSUBSCRIBE_LINK_INVALID,
            fields={"token": [_("Lien de désabonnement invalide.")]},
        ) from None
    return user, edition


@transaction.atomic
def unsubscribe(token: str, *, actor: Actor) -> Edition:
    """Lien du pied de page (jeton signé) : plus d'annonce par e-mail pour cette édition."""
    user, edition = _read_token(token)
    set_subscription(user, edition, subscribed=False, actor=actor)
    return edition


def is_subscribed(user: User, edition: Edition) -> bool:
    return not AnnouncementOptOut.objects.filter(user=user, edition=edition).exists()


@transaction.atomic
def set_subscription(user: User, edition: Edition, *, subscribed: bool, actor: Actor) -> bool:
    if subscribed:
        deleted, _rows = AnnouncementOptOut.objects.filter(user=user, edition=edition).delete()
        if deleted:
            record("announcement.resubscribed", actor=actor, edition=edition, obj=user)
    else:
        _row, created = AnnouncementOptOut.objects.get_or_create(user=user, edition=edition)
        if created:
            record("announcement.unsubscribed", actor=actor, edition=edition, obj=user)
    return subscribed


# --- Lectures publiques ------------------------------------------------------------------


def active_banner(edition: Edition, *, now: dt.datetime | None = None) -> Announcement | None:
    now = now or timezone.now()
    return (
        Announcement.objects.filter(
            edition=edition,
            status=AnnouncementStatus.PUBLISHED,
            on_banner=True,
            banner_starts_at__lte=now,
            banner_ends_at__gt=now,
        )
        .order_by("banner_starts_at", "id")
        .first()
    )


def news(edition: Edition) -> list[Announcement]:
    return list(
        Announcement.objects.filter(
            edition=edition, status=AnnouncementStatus.PUBLISHED, on_news=True
        ).order_by("-published_at", "-id")
    )
