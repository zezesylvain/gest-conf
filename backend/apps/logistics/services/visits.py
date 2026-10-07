"""Fiches de venue des intervenants invités (plan L8, N6 ; étude M10, §10.1).

- Intervenant invité : rôle ``SPEAKER`` actif dans l'édition. Il écrit **sa** part
  (besoins techniques, arrivée, départ, demandes) depuis le portail ; le CO « logistique »
  écrit tout, dont l'hôtel, le statut et la note interne, jamais servie à l'intervenant.
- Les heures se saisissent **en heure locale de l'édition** (D13) et sont stockées en UTC.
- Signal : besoin technique absent de l'équipement d'une salle où l'intervenant passe, lue
  dans le programme **publié** (L5).
- Journal ``visit.*`` sans note libre (elles peuvent contenir des données de voyage).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.conferences.services import local_to_utc
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.logistics.models import SpeakerVisit, TravelMeans, VisitStatus

NOTE_LIMIT = 1000
TEXT_LIMITS = {
    "technical_note": 500,
    "arrival_reference": 60,
    "departure_reference": 60,
    "speaker_note": NOTE_LIMIT,
    "hotel": 150,
    "internal_note": 2000,
}


def speakers(edition: Edition):
    """Intervenants invités de l'édition : rôle ``SPEAKER`` actif, comptes actifs."""
    holders = UserRole.objects.filter(
        edition=edition, role=Role.SPEAKER, status=UserRoleStatus.ACTIVE
    ).values("user_id")
    return User.objects.filter(pk__in=holders, is_active=True, anonymized_at__isnull=True)


def is_speaker(edition: Edition, user: User) -> bool:
    return speakers(edition).filter(pk=user.pk).exists()


def visit_of(edition: Edition, user: User) -> SpeakerVisit | None:
    return SpeakerVisit.objects.filter(edition=edition, user=user).first()


def _equipment_values() -> set[str]:
    from apps.program.models import Equipment

    return set(Equipment.values)


# Les instants se saisissent en heure locale de l'édition (D13) sous un autre nom.
INPUT_NAMES = {"arrival_at": "arrival_local", "departure_at": "departure_local"}


def _clean(edition: Edition, data: Mapping[str, Any], allowed: tuple[str, ...]) -> dict[str, Any]:
    accepted = {INPUT_NAMES.get(name, name) for name in allowed}
    unknown = set(data) - accepted
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    for name, limit in TEXT_LIMITS.items():
        if name in data:
            value = (data[name] or "").strip()
            if len(value) > limit:
                errors[name] = [_("%(limit)s caractères au plus.") % {"limit": limit}]
            clean[name] = value
    if "technical_needs" in data:
        needs = data["technical_needs"] or []
        if not isinstance(needs, list) or not set(needs) <= _equipment_values():
            errors["technical_needs"] = [_("Équipement inconnu.")]
        else:
            clean["technical_needs"] = sorted(set(needs))
    for name in ("arrival_means", "departure_means"):
        if name in data:
            if data[name] not in ("", *TravelMeans.values):
                errors[name] = [_("Moyen inconnu.")]
            clean[name] = data[name]
    for name in ("accommodation_needed", "transfer_needed"):
        if name in data:
            clean[name] = bool(data[name])
    for local, field in (("arrival_local", "arrival_at"), ("departure_local", "departure_at")):
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
    for name in ("check_in", "check_out"):
        if name in data:
            if data[name] is not None and not isinstance(data[name], dt.date):
                errors[name] = [_("Date attendue.")]
            clean[name] = data[name]
    if "status" in data:
        if data["status"] not in VisitStatus.values:
            errors["status"] = [_("Statut inconnu.")]
        clean["status"] = data["status"]
    if errors:
        raise Invalid(fields=errors)
    return clean


def _check_order(visit: SpeakerVisit) -> None:
    errors = {}
    if visit.arrival_at and visit.departure_at and visit.departure_at <= visit.arrival_at:
        errors["departure_local"] = [_("Départ après l'arrivée.")]
    if visit.check_in and visit.check_out and visit.check_out <= visit.check_in:
        errors["check_out"] = [_("Départ de l'hôtel après l'arrivée.")]
    if errors:
        raise Invalid(fields=errors)


def _changed(before: dict, visit: SpeakerVisit) -> list[str]:
    return [name for name in before if getattr(visit, name) != before[name]]


@transaction.atomic
def _write(
    edition: Edition, user: User, data: Mapping[str, Any], allowed: tuple[str, ...], actor: Actor
) -> SpeakerVisit:
    ensure_editable(edition)
    clean = _clean(edition, data, allowed)
    visit, _created = SpeakerVisit.objects.select_for_update().get_or_create(
        edition=edition, user=user
    )
    names = (*SpeakerVisit.SPEAKER_FIELDS, *SpeakerVisit.STAFF_FIELDS)
    before = {name: getattr(visit, name) for name in names}
    for name, value in clean.items():
        setattr(visit, name, value)
    _check_order(visit)
    visit.updated_by = actor.user
    visit.save()
    changed = _changed(before, visit)
    if changed:
        # Les champs changés seulement, sans valeur : les notes et références de voyage
        # restent hors du journal.
        record("visit.updated", actor=actor, edition=edition, obj=visit, after={"fields": changed})
    return visit


def update_by_speaker(
    edition: Edition, user: User, data: Mapping[str, Any], *, actor: Actor
) -> SpeakerVisit:
    """« Ma venue » : l'intervenant invité écrit sa part, rien d'autre."""
    if not is_speaker(edition, user):
        raise Invalid(
            fields={"edition": [_("Vous n'êtes pas intervenant invité de cette édition.")]}
        )
    return _write(edition, user, data, SpeakerVisit.SPEAKER_FIELDS, actor)


def update_by_staff(
    edition: Edition, user: User, data: Mapping[str, Any], *, actor: Actor
) -> SpeakerVisit:
    """Le CO « logistique » écrit toute la fiche d'un intervenant invité."""
    if not is_speaker(edition, user):
        raise Invalid(fields={"speaker": [_("Intervenant invité de l'édition attendu.")]})
    return _write(
        edition,
        user,
        data,
        (*SpeakerVisit.SPEAKER_FIELDS, *SpeakerVisit.STAFF_FIELDS),
        actor,
    )


def missing_equipment(edition: Edition) -> dict[int, list[str]]:
    """Besoins techniques de chaque intervenant absents de l'équipement d'une salle où il
    passe (programme publié) : ``{compte: [équipements manquants]}``."""
    from apps.program.models import Room
    from apps.program.services.publication import latest_publication, passages

    publication = latest_publication(edition)
    if publication is None:
        return {}
    rooms_by_session = {
        item["id"]: (item.get("room") or {}).get("id") for item in publication.snapshot["sessions"]
    }
    equipment = {room.pk: set(room.equipment) for room in Room.objects.filter(edition=edition)}
    result: dict[int, list[str]] = {}
    needs = {
        visit.user_id: set(visit.technical_needs)
        for visit in SpeakerVisit.objects.filter(edition=edition).exclude(technical_needs=[])
    }
    for key, items in passages(publication.snapshot).items():
        kind, _sep, value = key.partition(":")
        if kind != "user" or int(value) not in needs:
            continue
        user_id = int(value)
        missing: set[str] = set()
        for passage in items:
            room = rooms_by_session.get(passage.session)
            if room is not None:
                missing |= needs[user_id] - equipment.get(room, set())
        if missing:
            result[user_id] = sorted(missing)
    return result


def erase_after_edition(dry_run: bool, now) -> int:
    """Tâche de conservation (N15) : fiches de venue des éditions archivées ou finies depuis
    30 jours, effacées."""
    from apps.logistics.services.dietary import retention_filter

    rows = SpeakerVisit.objects.filter(retention_filter(now))
    count = rows.count()
    if not dry_run and count:
        rows.delete()
    return count
