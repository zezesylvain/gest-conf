"""Planning des bénévoles (plan L8, N9 ; étude M10).

- Postes : intitulé FR et EN, lieu, début et fin **saisis en heure locale de l'édition** (D13),
  nombre de bénévoles nécessaires, consignes.
- Affectation d'un bénévole (rôle ``VOLUNTEER`` actif de l'édition) : deux postes qui se
  chevauchent pour la même personne sont refusés ; le compte du bénévole est verrouillé le
  temps de la vérification (deux affectations simultanées ne passent pas toutes les deux).
- Cloche au bénévole à chaque affectation (``shift_assigned``) et à chaque retrait
  (``shift_removed``, y compris par suppression du poste) ; « Mon planning »
  (``shifts.own``) et son iCal.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.roles import ensure_editable
from apps.communications.models import NotificationKind
from apps.communications.notifications import notify
from apps.conferences.models import Edition
from apps.conferences.services import local_to_utc
from apps.core.actor import Actor
from apps.core.audit import mask_emails, record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.logistics.models import ShiftAssignment, VolunteerShift

FIELDS = frozenset(
    {"title_fr", "title_en", "place", "starts_local", "ends_local", "needed", "instructions"}
)
TEXT_LIMITS = {"title_fr": 150, "title_en": 150, "place": 150, "instructions": 1000}


def volunteers(edition: Edition):
    holders = UserRole.objects.filter(
        edition=edition, role=Role.VOLUNTEER, status=UserRoleStatus.ACTIVE
    ).values("user_id")
    return User.objects.filter(pk__in=holders, is_active=True, anonymized_at__isnull=True)


def _clean(edition: Edition, data: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    unknown = set(data) - FIELDS
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
    if (creating or "title_fr" in clean) and not clean.get("title_fr"):
        errors["title_fr"] = [_("Intitulé obligatoire.")]
    for local, field in (("starts_local", "starts_at"), ("ends_local", "ends_at")):
        if local in data or creating:
            value = data.get(local)
            if not isinstance(value, dt.datetime):
                errors[local] = [_("Date et heure attendues.")]
                continue
            try:
                clean[field] = local_to_utc(value, edition.timezone)
            except Invalid as error:
                errors[local] = list(error.fields.get("at_local", [error.message]))
    if "needed" in data or creating:
        needed = data.get("needed", 1)
        if not isinstance(needed, int) or isinstance(needed, bool) or not 1 <= needed <= 100:
            errors["needed"] = [_("De 1 à 100 bénévoles.")]
        clean["needed"] = needed
    if errors:
        raise Invalid(fields=errors)
    return clean


def _snapshot(shift: VolunteerShift) -> dict[str, Any]:
    return mask_emails(
        {
            "title_fr": shift.title_fr,
            "place": shift.place,
            "starts_at": shift.starts_at.isoformat(),
            "ends_at": shift.ends_at.isoformat(),
            "needed": shift.needed,
        }
    )


def _check_times(shift: VolunteerShift) -> None:
    if shift.ends_at <= shift.starts_at:
        raise Invalid(fields={"ends_local": [_("Fin après le début.")]})


def _overlaps(volunteer: User, shift: VolunteerShift) -> bool:
    return (
        ShiftAssignment.objects.filter(
            volunteer=volunteer,
            shift__edition_id=shift.edition_id,
            shift__starts_at__lt=shift.ends_at,
            shift__ends_at__gt=shift.starts_at,
        )
        .exclude(shift=shift)
        .exists()
    )


@transaction.atomic
def create_shift(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> VolunteerShift:
    ensure_editable(edition)
    shift = VolunteerShift(edition=edition, **_clean(edition, data, creating=True))
    _check_times(shift)
    shift.save()
    record("shift.created", actor=actor, edition=edition, obj=shift, after=_snapshot(shift))
    return shift


@transaction.atomic
def update_shift(shift: VolunteerShift, data: Mapping[str, Any], *, actor: Actor) -> VolunteerShift:
    ensure_editable(shift.edition)
    shift = VolunteerShift.objects.select_for_update().select_related("edition").get(pk=shift.pk)
    before = _snapshot(shift)
    for name, value in _clean(shift.edition, data, creating=False).items():
        setattr(shift, name, value)
    _check_times(shift)
    # Un horaire déplacé ne doit pas créer de chevauchement pour un bénévole déjà affecté.
    for assignment in shift.assignments.select_related("volunteer"):
        if _overlaps(assignment.volunteer, shift):
            raise RuleViolation(
                _("Ce nouvel horaire chevaucherait un autre poste d'un bénévole affecté."),
                code=ErrorCode.SHIFT_OVERLAP,
            )
    shift.save()
    after = _snapshot(shift)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "shift.updated",
            actor=actor,
            edition=shift.edition,
            obj=shift,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return shift


def _payload(shift: VolunteerShift) -> dict[str, Any]:
    return {
        "edition_id": shift.edition_id,
        "edition_code": shift.edition.code,
        "shift_id": shift.pk,
        "title": shift.title_fr,
        "starts_at": shift.starts_at.isoformat(),
    }


@transaction.atomic
def delete_shift(shift: VolunteerShift, *, actor: Actor) -> None:
    ensure_editable(shift.edition)
    shift = VolunteerShift.objects.select_for_update().select_related("edition").get(pk=shift.pk)
    record("shift.deleted", actor=actor, edition=shift.edition, obj=shift, before=_snapshot(shift))
    payload = _payload(shift)
    for assignment in shift.assignments.select_related("volunteer"):
        notify(assignment.volunteer, NotificationKind.SHIFT_REMOVED, payload)
    shift.delete()


@transaction.atomic
def assign(shift: VolunteerShift, volunteer_id: int, *, actor: Actor) -> ShiftAssignment:
    ensure_editable(shift.edition)
    volunteer = volunteers(shift.edition).select_for_update().filter(pk=volunteer_id).first()
    if volunteer is None:
        raise Invalid(fields={"volunteer": [_("Bénévole de l'édition attendu.")]})
    shift = VolunteerShift.objects.select_related("edition").get(pk=shift.pk)
    existing = shift.assignments.filter(volunteer=volunteer).first()
    if existing is not None:
        return existing  # déjà affecté : sans effet
    if _overlaps(volunteer, shift):
        raise RuleViolation(
            _("Ce bénévole est déjà affecté à un poste au même moment."),
            code=ErrorCode.SHIFT_OVERLAP,
        )
    assignment = ShiftAssignment.objects.create(
        shift=shift, volunteer=volunteer, assigned_by=actor.user
    )
    record(
        "shift.assigned",
        actor=actor,
        edition=shift.edition,
        obj=shift,
        after={"volunteer": volunteer.pk},
    )
    notify(volunteer, NotificationKind.SHIFT_ASSIGNED, _payload(shift))
    return assignment


@transaction.atomic
def unassign(shift: VolunteerShift, volunteer_id: int, *, actor: Actor) -> None:
    ensure_editable(shift.edition)
    assignment = (
        ShiftAssignment.objects.select_related("volunteer", "shift__edition")
        .filter(shift=shift, volunteer_id=volunteer_id)
        .first()
    )
    if assignment is None:
        return  # pas affecté : sans effet
    assignment.delete()
    record(
        "shift.unassigned",
        actor=actor,
        edition=shift.edition,
        obj=shift,
        before={"volunteer": volunteer_id},
    )
    notify(assignment.volunteer, NotificationKind.SHIFT_REMOVED, _payload(assignment.shift))


def my_shifts(edition: Edition, user: User) -> list[VolunteerShift]:
    return list(
        VolunteerShift.objects.filter(edition=edition, assignments__volunteer=user)
        .select_related("edition")
        .order_by("starts_at", "id")
    )


def calendar(edition: Edition, user: User, *, now: dt.datetime) -> str:
    """Fichier ``.ics`` du planning d'un bénévole (générateur de L5)."""
    from apps.program import ical

    host = urlparse(settings.GESTCONF_PUBLIC_URL).hostname or "gest-conf"
    events = [
        ical.Event(
            uid=f"{edition.code}-shift-{shift.pk}-{user.pk}@{host}",
            starts_at=shift.starts_at,
            ends_at=shift.ends_at,
            summary=f"{edition.code} · {shift.title_fr}",
            location=shift.place,
            description=shift.instructions,
        )
        for shift in my_shifts(edition, user)
    ]
    return ical.calendar(events, stamp=now, name=f"{edition.code} · bénévolat")
