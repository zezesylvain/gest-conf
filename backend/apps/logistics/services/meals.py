"""Repas et estimation des effectifs (plan L8, N8 ; étude M10).

L'effectif d'un repas est **calculé** : les personnes de son public (inscrits confirmés, ou
titulaires d'une option de L6 ; intervenants invités ; membres des comités ; bénévoles),
chacune une fois, avec la répartition par régime (RG-23 : agrégée, sans nom) et la marge.
Les repas réellement servis ne sont pas suivis.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from typing import Any

from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import mask_emails, record
from apps.core.errors import Invalid
from apps.logistics.models import DietaryDeclaration, Meal, MealKind
from apps.logistics.services.dietary import counts

COMMITTEE_ROLES = (Role.ADMIN, Role.CHAIR, Role.OC_MEMBER, Role.SC_CHAIR, Role.SC_MEMBER)
FIELDS = frozenset(
    {
        "day",
        "kind",
        "label_fr",
        "label_en",
        "include_registered",
        "option_code",
        "include_speakers",
        "include_committees",
        "include_volunteers",
        "margin_percent",
        "position",
    }
)


def _clean(edition: Edition, data: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    from apps.registrations.models import RegistrationOption

    unknown = set(data) - FIELDS
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    if "day" in data or creating:
        day = data.get("day")
        if not isinstance(day, dt.date):
            errors["day"] = [_("Date attendue.")]
        elif (
            edition.start_date
            and edition.end_date
            and not (edition.start_date <= day <= edition.end_date)
        ):
            errors["day"] = [_("Jour en dehors des dates de l'édition.")]
        clean["day"] = day
    if "kind" in data or creating:
        if data.get("kind") not in MealKind.values:
            errors["kind"] = [_("Type de repas inconnu.")]
        clean["kind"] = data.get("kind")
    for name in ("label_fr", "label_en"):
        if name in data:
            value = (data[name] or "").strip()
            if len(value) > 150:
                errors[name] = [_("150 caractères au plus.")]
            clean[name] = value
    for name in (
        "include_registered",
        "include_speakers",
        "include_committees",
        "include_volunteers",
    ):
        if name in data:
            clean[name] = bool(data[name])
    if "option_code" in data:
        code = (data["option_code"] or "").strip()
        if code and not RegistrationOption.objects.filter(edition=edition, code=code).exists():
            errors["option_code"] = [_("Option d'inscription inconnue.")]
        clean["option_code"] = code
    if "margin_percent" in data:
        margin = data["margin_percent"]
        if not isinstance(margin, int) or isinstance(margin, bool) or not 0 <= margin <= 50:
            errors["margin_percent"] = [_("Marge de 0 à 50 %.")]
        clean["margin_percent"] = margin
    if "position" in data:
        position = data["position"]
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            errors["position"] = [_("Position positive ou nulle attendue.")]
        clean["position"] = position
    if errors:
        raise Invalid(fields=errors)
    return clean


def _snapshot(meal: Meal) -> dict[str, Any]:
    values = {name: getattr(meal, name) for name in FIELDS}
    values["day"] = meal.day.isoformat() if meal.day else None
    return mask_emails(values)


@transaction.atomic
def create_meal(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Meal:
    ensure_editable(edition)
    meal = Meal.objects.create(edition=edition, **_clean(edition, data, creating=True))
    record("meal.created", actor=actor, edition=edition, obj=meal, after=_snapshot(meal))
    return meal


@transaction.atomic
def update_meal(meal: Meal, data: Mapping[str, Any], *, actor: Actor) -> Meal:
    ensure_editable(meal.edition)
    meal = Meal.objects.select_for_update().select_related("edition").get(pk=meal.pk)
    clean = _clean(meal.edition, data, creating=False)
    before = _snapshot(meal)
    for name, value in clean.items():
        setattr(meal, name, value)
    meal.save()
    after = _snapshot(meal)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "meal.updated",
            actor=actor,
            edition=meal.edition,
            obj=meal,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return meal


@transaction.atomic
def delete_meal(meal: Meal, *, actor: Actor) -> None:
    ensure_editable(meal.edition)
    record("meal.deleted", actor=actor, edition=meal.edition, obj=meal, before=_snapshot(meal))
    meal.delete()


def attendees(meal: Meal) -> set[int]:
    """Comptes du public du repas, chacun une fois."""
    from apps.registrations.models import Registration, RegistrationStatus

    people: set[int] = set()
    if meal.include_registered:
        registrations = Registration.objects.filter(
            edition=meal.edition, status=RegistrationStatus.CONFIRMED
        )
        if meal.option_code:
            registrations = registrations.filter(options__code=meal.option_code)
        people |= set(registrations.values_list("user_id", flat=True))
    roles: list[str] = []
    if meal.include_speakers:
        roles.append(Role.SPEAKER)
    if meal.include_committees:
        roles.extend(COMMITTEE_ROLES)
    if meal.include_volunteers:
        roles.append(Role.VOLUNTEER)
    if roles:
        people |= set(
            UserRole.objects.filter(
                edition=meal.edition,
                status=UserRoleStatus.ACTIVE,
                role__in=roles,
                user__is_active=True,
                user__anonymized_at__isnull=True,
            ).values_list("user_id", flat=True)
        )
    return people


def estimate(meal: Meal) -> dict[str, Any]:
    """Effectif, marge, total à commander, répartition par régime (sans nom)."""
    people = attendees(meal)
    declarations = DietaryDeclaration.objects.filter(edition=meal.edition, user_id__in=people)
    count = len(people)
    margin = math.ceil(count * meal.margin_percent / 100)
    return {"count": count, "margin": margin, "total": count + margin, **counts(declarations)}


def export_rows(edition: Edition) -> tuple[list[str], list[list[Any]]]:
    """Commande au traiteur (agrégée, sans nom), dans la langue de la requête."""
    from django.utils.translation import gettext

    from apps.logistics.models import Diet

    header = [
        gettext("Jour"),
        gettext("Repas"),
        gettext("Libellé"),
        gettext("Effectif"),
        gettext("Marge"),
        gettext("Total"),
        *[str(label) for _value, label in Diet.choices],
        gettext("Allergies"),
    ]
    rows = []
    for meal in Meal.objects.filter(edition=edition).select_related("edition"):
        data = estimate(meal)
        rows.append(
            [
                meal.day.isoformat(),
                str(MealKind(meal.kind).label),
                meal.label_fr,
                data["count"],
                data["margin"],
                data["total"],
                *[data["by_diet"][diet] for diet in data["by_diet"]],
                data["allergies"],
            ]
        )
    return header, rows
