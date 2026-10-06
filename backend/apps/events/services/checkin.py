"""Pointage à l'accueil (plan L7, K2, K4, K5 ; RG-16).

Un pointage vaut **présence à la conférence**. Il se fait par le QR du badge (jeton
d'inscription, ``checkin.scan``) ou par la référence de l'inscription (saisie manuelle,
``checkin.manage`` : une référence se devine, un jeton non).

- **Preuve** : le serveur n'accepte que le jeton lui-même, jamais son empreinte. La liste
  hors ligne ne contient que des empreintes : elle ne permet donc pas de pointer qui que ce
  soit sans son badge.
- **Refus explicites et distincts** : jeton inconnu, autre édition, inscription annulée ou
  expirée, badge remplacé, en attente de paiement (K4, réponse du commanditaire : refus et
  renvoi au comptoir). Déjà pointé : avertissement, sans nouvelle ligne.
- **Idempotence** : chaque pointage porte une clé de l'appareil ; rejouer la même clé
  renvoie le même résultat (synchronisation hors ligne, K5).
- **Horodatage** : heure de l'appareil, bornée à la réception et aux 24 heures qui la
  précèdent ; l'heure de réception est gardée à part.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.invitations import display_name
from apps.accounts.services.roles import ensure_editable
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.events.models import Checkin, CheckinMethod
from apps.registrations.models import (
    Registration,
    RegistrationStatus,
    RetiredQrToken,
    RetiredTokenReason,
)
from apps.registrations.tokens import token_hash

if TYPE_CHECKING:
    from apps.conferences.models import Edition
    from apps.core.actor import Actor

# Liste hors ligne : durée de vie dans l'appareil (K5).
BUNDLE_LIFETIME = dt.timedelta(hours=48)
# Heure de l'appareil acceptée jusqu'à 24 heures avant la réception (K4).
MAX_DEVICE_DELAY = dt.timedelta(hours=24)
# Synchronisation : taille d'un lot (K5, §6 « bornée »).
SYNC_MAX_ITEMS = 200
IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
REFERENCE = re.compile(r"^(?P<edition>[A-Za-z0-9_-]+)-I(?P<number>\d{1,10})$")


class Outcome:
    """Résultat d'un pointage (``CHECKIN_OUTCOME_CHOICES`` dans le schéma)."""

    CHECKED_IN = "checked_in"
    ALREADY_CHECKED_IN = "already_checked_in"
    UNKNOWN = "unknown"
    OTHER_EDITION = "other_edition"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REPLACED = "replaced"
    PENDING_PAYMENT = "pending_payment"
    NOT_ALLOWED = "not_allowed"


OUTCOME_CHOICES = [
    (Outcome.CHECKED_IN, _("pointé")),
    (Outcome.ALREADY_CHECKED_IN, _("déjà pointé")),
    (Outcome.UNKNOWN, _("badge inconnu")),
    (Outcome.OTHER_EDITION, _("badge d'une autre édition")),
    (Outcome.CANCELLED, _("inscription annulée")),
    (Outcome.EXPIRED, _("inscription expirée")),
    (Outcome.REPLACED, _("badge remplacé")),
    (Outcome.PENDING_PAYMENT, _("en attente de paiement")),
    (Outcome.NOT_ALLOWED, _("saisie manuelle non permise")),
]
# Résultats où la personne est (ou était déjà) pointée.
ADMITTED = frozenset({Outcome.CHECKED_IN, Outcome.ALREADY_CHECKED_IN})
_STATUS_OUTCOMES = {
    RegistrationStatus.PENDING: Outcome.PENDING_PAYMENT,
    RegistrationStatus.CANCELLED: Outcome.CANCELLED,
    RegistrationStatus.EXPIRED: Outcome.EXPIRED,
}


@dataclass(frozen=True, slots=True)
class CheckinResult:
    outcome: str
    idempotency_key: str
    registration: Registration | None = None
    checkin: Checkin | None = None


# --- Résolution du badge ou de la référence ---------------------------------------------------


def _registrations():
    return Registration.objects.select_related("edition", "category", "user__profile")


def resolve_token(edition: Edition, token: str) -> tuple[str | None, Registration | None]:
    """Jeton lu sur le badge → (refus éventuel, inscription). ``None`` : pointable."""
    registration = _registrations().filter(qr_token=token).first() if token else None
    if registration is None:
        retired = (
            RetiredQrToken.objects.select_related(
                "registration__edition", "registration__category", "registration__user__profile"
            )
            .filter(token_hash=token_hash(token))
            .first()
            if token
            else None
        )
        if retired is None:
            return Outcome.UNKNOWN, None
        registration = retired.registration
        if registration.edition_id != edition.pk:
            return Outcome.OTHER_EDITION, None
        if retired.reason == RetiredTokenReason.REPLACED:
            return Outcome.REPLACED, registration
        return Outcome.CANCELLED, registration
    if registration.edition_id != edition.pk:
        return Outcome.OTHER_EDITION, None
    return None, registration


def parse_reference(reference: str) -> tuple[str, int] | None:
    """« GC27-I00042 » → (code d'édition, rang) ; ``None`` si mal formée."""
    match = REFERENCE.match(reference.strip().upper())
    if match is None:
        return None
    return match["edition"], int(match["number"])


def resolve_reference(edition: Edition, reference: str) -> tuple[str | None, Registration | None]:
    parsed = parse_reference(reference)
    if parsed is None or parsed[0] != edition.code.upper():
        return Outcome.UNKNOWN, None
    registration = _registrations().filter(edition=edition, pk=parsed[1]).first()
    if registration is None:
        return Outcome.UNKNOWN, None
    return None, registration


# --- Pointage -------------------------------------------------------------------------------------


def bounded_scan_time(scanned_at: dt.datetime | None, received_at: dt.datetime) -> dt.datetime:
    """Heure de l'appareil ramenée dans [réception moins 24 h, réception] (horloge déréglée)."""
    if scanned_at is None:
        return received_at
    return max(received_at - MAX_DEVICE_DELAY, min(scanned_at, received_at))


def active_checkin(registration: Registration, session_id: int | None = None) -> Checkin | None:
    return (
        Checkin.objects.select_related("recorded_by__profile")
        .filter(active_key=Checkin.place_key(registration.pk, session_id))
        .first()
    )


def _replay(edition: Edition, key: str) -> CheckinResult | None:
    """Clé déjà reçue : même résultat qu'à la première réception (synchronisation rejouée)."""
    existing = (
        Checkin.objects.select_related(
            "registration__edition",
            "registration__category",
            "registration__user__profile",
            "recorded_by__profile",
        )
        .filter(idempotency_key=key)
        .first()
    )
    if existing is None:
        return None
    if existing.edition_id != edition.pk:
        raise Invalid(fields={"idempotency_key": [_("Clé déjà utilisée.")]})
    return CheckinResult(
        Outcome.CHECKED_IN, key, registration=existing.registration, checkin=existing
    )


@transaction.atomic
def _check_in(
    edition: Edition,
    registration: Registration,
    *,
    method: str,
    scanned_at: dt.datetime | None,
    device: str,
    key: str,
    actor: Actor,
) -> CheckinResult:
    # Verrou de l'inscription : deux appareils qui lisent le même badge en même temps
    # produisent un pointage et un « déjà pointé ».
    registration = _registrations().select_for_update().get(pk=registration.pk)
    if registration.status != RegistrationStatus.CONFIRMED:
        return CheckinResult(_STATUS_OUTCOMES[registration.status], key, registration)
    existing = active_checkin(registration)
    if existing is not None:
        return CheckinResult(Outcome.ALREADY_CHECKED_IN, key, registration, existing)
    now = timezone.now()
    checkin = Checkin.objects.create(
        edition=edition,
        registration=registration,
        session=None,
        scanned_at=bounded_scan_time(scanned_at, now),
        received_at=now,
        recorded_by=actor.user,
        method=method,
        device=device[:64],
        idempotency_key=key,
        active_key=Checkin.place_key(registration.pk, None),
    )
    record("checkin.recorded", actor=actor, edition=edition, obj=checkin, after=snapshot(checkin))
    return CheckinResult(Outcome.CHECKED_IN, key, registration, checkin)


def check_in(
    edition: Edition,
    *,
    token: str = "",
    reference: str = "",
    method: str = CheckinMethod.SCAN,
    scanned_at: dt.datetime | None = None,
    device: str = "",
    idempotency_key: str = "",
    actor: Actor,
) -> CheckinResult:
    """Pointe à l'accueil par le jeton du badge (``scan``) ou la référence (``manual``).

    Les droits (``checkin.scan`` ou ``checkin.manage``) sont vérifiés par la vue ; la
    synchronisation les revérifie élément par élément (``synchronize``).
    """
    ensure_editable(edition)
    key = idempotency_key or uuid.uuid4().hex
    if not IDEMPOTENCY_KEY.match(key):
        raise Invalid(fields={"idempotency_key": [_("Clé mal formée.")]})
    replay = _replay(edition, key)
    if replay is not None:
        return replay
    if method == CheckinMethod.SCAN:
        refusal, registration = resolve_token(edition, token)
    else:
        refusal, registration = resolve_reference(edition, reference)
    if refusal is not None or registration is None:
        return CheckinResult(refusal or Outcome.UNKNOWN, key, registration)
    try:
        return _check_in(
            edition,
            registration,
            method=method,
            scanned_at=scanned_at,
            device=device,
            key=key,
            actor=actor,
        )
    except IntegrityError:
        # Course rare : la même clé reçue deux fois en même temps.
        replay = _replay(edition, key)
        if replay is None:
            raise
        return replay


def synchronize(
    edition: Edition,
    items: Sequence[dict[str, Any]],
    *,
    device: str,
    may_enter_manually: bool,
    actor: Actor,
) -> list[CheckinResult]:
    """File de pointages hors ligne (K5) : chaque élément est revérifié par le serveur
    (règle n° 2) ; une saisie manuelle exige ``checkin.manage``. Rejouable sans doublon."""
    if len(items) > SYNC_MAX_ITEMS:
        raise Invalid(fields={"items": [_("200 pointages au plus par envoi.")]})
    results = []
    for item in items:
        method = item.get("method", CheckinMethod.SCAN)
        if method == CheckinMethod.MANUAL and not may_enter_manually:
            results.append(CheckinResult(Outcome.NOT_ALLOWED, item["idempotency_key"]))
            continue
        results.append(
            check_in(
                edition,
                token=item.get("token", ""),
                reference=item.get("reference", ""),
                method=method,
                scanned_at=item.get("scanned_at"),
                device=device,
                idempotency_key=item["idempotency_key"],
                actor=actor,
            )
        )
    return results


@transaction.atomic
def cancel_checkin(checkin: Checkin, *, reason: str, actor: Actor) -> Checkin:
    """Annule un pointage (erreur de l'accueil) : motif obligatoire, journal ; la personne
    peut être pointée de nouveau. Rien n'est supprimé."""
    ensure_editable(checkin.edition)
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    checkin = Checkin.objects.select_for_update().get(pk=checkin.pk)
    if checkin.cancelled_at is not None:
        raise RuleViolation(_("Pointage déjà annulé."), code=ErrorCode.INVALID_TRANSITION)
    before = snapshot(checkin)
    checkin.cancelled_at = timezone.now()
    checkin.cancelled_by = actor.user
    checkin.cancel_reason = reason.strip()[:500]
    checkin.active_key = None
    checkin.save()
    record(
        "checkin.cancelled",
        actor=actor,
        edition=checkin.edition,
        obj=checkin,
        before=before,
        after=snapshot(checkin),
        reason=reason,
    )
    return checkin


# --- Liste hors ligne (K5) -----------------------------------------------------------------------


def person_name(registration: Registration) -> str:
    return display_name(registration.user)


def offline_bundle(edition: Edition, *, actor: Actor) -> dict[str, Any]:
    """Liste de pointage minimale : empreinte du jeton, référence, nom, catégorie, déjà
    pointé ; ni adresse, ni institution, ni jeton. Badges retirés : empreinte et motif.
    Téléchargement journalisé (qui, quand, combien)."""
    now = timezone.now()
    checked = set(
        Checkin.objects.filter(
            edition=edition, session__isnull=True, active_key__isnull=False
        ).values_list("registration_id", flat=True)
    )
    rows = (
        _registrations()
        .filter(edition=edition, status=RegistrationStatus.CONFIRMED, qr_token__isnull=False)
        .order_by("id")
    )
    entries = [
        {
            "token_hash": token_hash(row.qr_token),
            "reference": row.reference,
            "name": person_name(row),
            "category": row.category.code,
            "checked_in": row.pk in checked,
        }
        for row in rows
    ]
    retired = [
        {
            "token_hash": item.token_hash,
            "reference": item.registration.reference,
            "reason": item.reason,
        }
        for item in RetiredQrToken.objects.select_related("registration__edition")
        .filter(registration__edition=edition)
        .order_by("id")
    ]
    categories = [
        {"code": code, "label_fr": label_fr, "label_en": label_en or label_fr}
        for code, label_fr, label_en in edition.registration_categories.order_by(
            "position", "id"
        ).values_list("code", "label_fr", "label_en")
    ]
    record(
        "checkin.bundle_downloaded",
        actor=actor,
        edition=edition,
        after={"entries": len(entries), "retired": len(retired)},
    )
    return {
        "edition_id": edition.pk,
        "generated_at": now,
        "expires_at": now + BUNDLE_LIFETIME,
        "categories": categories,
        "entries": entries,
        "retired": retired,
    }


# --- Suivi et export ----------------------------------------------------------------------------


def summary(edition: Edition) -> dict[str, int]:
    """Compteurs de l'accueil : inscriptions confirmées, pointées, en attente de paiement."""
    counts = Registration.objects.filter(edition=edition).aggregate(
        confirmed=Count("pk", filter=Q(status=RegistrationStatus.CONFIRMED)),
        pending=Count("pk", filter=Q(status=RegistrationStatus.PENDING)),
    )
    counts["checked_in"] = Checkin.objects.filter(
        edition=edition,
        session__isnull=True,
        active_key__isnull=False,
        registration__status=RegistrationStatus.CONFIRMED,
    ).count()
    return counts


def checkins(edition: Edition, *, query: str = "", include_cancelled: bool = False):
    rows = (
        Checkin.objects.filter(edition=edition, session__isnull=True)
        .select_related(
            "registration__edition",
            "registration__category",
            "registration__user__profile",
            "recorded_by__profile",
            "cancelled_by__profile",
        )
        .order_by("-received_at", "-id")
    )
    if not include_cancelled:
        rows = rows.filter(cancelled_at__isnull=True)
    query = query.strip()
    if query:
        condition = Q(registration__user__profile__last_name__icontains=query) | Q(
            registration__user__profile__first_name__icontains=query
        )
        parsed = parse_reference(query)
        if parsed is not None:
            condition |= Q(registration_id=parsed[1])
        rows = rows.filter(condition)
    return rows


EXPORT_HEADER = (
    _("Référence"),
    _("Nom"),
    _("Catégorie"),
    _("Pointé le (UTC)"),
    _("Reçu le (UTC)"),
    _("Moyen"),
    _("Pointé par"),
    _("Appareil"),
)


def export_rows(rows: Iterable[Checkin]) -> Iterable[list[Any]]:
    for row in rows:
        yield [
            row.registration.reference,
            person_name(row.registration),
            row.registration.category.code,
            row.scanned_at.isoformat(),
            row.received_at.isoformat(),
            row.method,
            display_name(row.recorded_by),
            row.device,
        ]
