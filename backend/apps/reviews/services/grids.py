"""Grilles d'évaluation (RG-05 ; plan L4, H3).

Par édition, et facultativement par type de communication (sinon la grille « toutes ») ;
critères bilingues, poids décimaux dont la somme vaut **exactement** 100 ; échelle par grille.
Une grille est verrouillée dès la première évaluation enregistrée : on la duplique en nouvelle
version, et les évaluations gardent la version qu'elles ont utilisée.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, SubmissionType
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.reviews.models import Criterion, EvaluationGrid

HUNDRED = Decimal("100")
MAX_CRITERIA = 20
GRID_FIELDS = ("name", "scale_min", "scale_max")
CRITERION_FIELDS = (
    "code",
    "label_fr",
    "label_en",
    "help_fr",
    "help_en",
    "weight",
    "is_required",
)

# Grille par défaut de l'étude (§5.1) : 25 / 30 / 15 / 15 / 15, échelle 0 à 5.
DEFAULT_CRITERIA: tuple[dict[str, Any], ...] = (
    {
        "code": "originalite",
        "label_fr": "Originalité et contribution scientifique",
        "label_en": "Originality and scientific contribution",
        "weight": Decimal("25"),
    },
    {
        "code": "methode",
        "label_fr": "Rigueur méthodologique",
        "label_en": "Methodological rigour",
        "weight": Decimal("30"),
    },
    {
        "code": "pertinence",
        "label_fr": "Pertinence par rapport aux thématiques",
        "label_en": "Relevance to the tracks",
        "weight": Decimal("15"),
    },
    {
        "code": "redaction",
        "label_fr": "Qualité de la rédaction et de la structure",
        "label_en": "Quality of writing and structure",
        "weight": Decimal("15"),
    },
    {
        "code": "impact",
        "label_fr": "Résultats, portée et impact",
        "label_en": "Results, scope and impact",
        "weight": Decimal("15"),
    },
)


def _writable(edition: Edition, actor: Actor) -> None:
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)


def _scope_key(edition_id: int, type_id: int | None, version: int) -> str:
    return f"{edition_id}:{type_id or 'all'}:{version}"


def _check_unlocked(grid: EvaluationGrid) -> None:
    if grid.locked_at is not None:
        raise RuleViolation(
            _("Grille déjà utilisée par une évaluation : dupliquez-la en nouvelle version."),
            code=ErrorCode.GRID_LOCKED,
        )


def _check_scale(scale_min: int, scale_max: int) -> None:
    if not 0 <= scale_min < scale_max <= 100:
        raise Invalid(fields={"scale_max": [_("Échelle invalide : 0 ≤ minimum < maximum ≤ 100.")]})


def clean_criteria(criteria: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """RG-05 : liste complète et ordonnée de critères ; codes uniques, poids positifs à deux
    décimales au plus, **somme exactement égale à 100**."""
    if not 1 <= len(criteria) <= MAX_CRITERIA:
        raise Invalid(fields={"criteria": [_("De 1 à 20 critères.")]})
    cleaned: list[dict[str, Any]] = []
    codes: set[str] = set()
    total = Decimal(0)
    for index, item in enumerate(criteria):
        unknown = set(item) - set(CRITERION_FIELDS)
        if unknown:
            raise Invalid(fields={"criteria": [_("Champ de critère inconnu.")]})
        code = str(item.get("code", "")).strip()
        if not code or code in codes:
            raise Invalid(fields={"criteria": [_("Codes de critère obligatoires et uniques.")]})
        try:
            weight = Decimal(str(item.get("weight")))
        except (InvalidOperation, TypeError) as error:
            raise Invalid(fields={"criteria": [_("Poids décimal attendu.")]}) from error
        if weight <= 0 or weight > HUNDRED or weight != weight.quantize(Decimal("0.01")):
            raise Invalid(
                fields={"criteria": [_("Poids entre 0,01 et 100, deux décimales au plus.")]}
            )
        label_fr = str(item.get("label_fr", "")).strip()
        if not label_fr:
            raise Invalid(fields={"criteria": [_("Libellé français obligatoire.")]})
        codes.add(code)
        total += weight
        cleaned.append(
            {
                "code": code,
                "label_fr": label_fr,
                "label_en": str(item.get("label_en", "")).strip(),
                "help_fr": str(item.get("help_fr", "")).strip(),
                "help_en": str(item.get("help_en", "")).strip(),
                "weight": weight,
                "is_required": bool(item.get("is_required", True)),
                "position": index,
            }
        )
    if total != HUNDRED:
        raise Invalid(
            fields={
                "criteria": [
                    _("La somme des poids doit valoir 100 (actuellement %(total)s).")
                    % {"total": total}
                ]
            }
        )
    return cleaned


def _write_criteria(grid: EvaluationGrid, criteria: list[dict[str, Any]]) -> None:
    grid.criteria.all().delete()
    Criterion.objects.bulk_create(Criterion(grid=grid, **item) for item in criteria)


def _criteria_snapshot(grid: EvaluationGrid) -> list[dict[str, Any]]:
    return [
        {"code": c.code, "weight": str(c.weight), "is_required": c.is_required}
        for c in grid.criteria.order_by("position", "id")
    ]


@transaction.atomic
def create_grid(
    edition: Edition,
    *,
    name: str,
    actor: Actor,
    submission_type: SubmissionType | None = None,
    scale_min: int = 0,
    scale_max: int = 5,
    criteria: Sequence[Mapping[str, Any]] | None = None,
) -> EvaluationGrid:
    """Nouvelle grille (version suivante pour ce type, ou pour « tous ») ; critères de la
    grille par défaut de l'étude si aucun n'est fourni."""
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    _writable(edition, actor)
    if submission_type is not None and submission_type.edition_id != edition.pk:
        raise Invalid(fields={"submission_type": [_("Type d'une autre édition.")]})
    if not name.strip():
        raise Invalid(fields={"name": [_("Nom obligatoire.")]})
    _check_scale(scale_min, scale_max)
    cleaned = clean_criteria(criteria if criteria is not None else DEFAULT_CRITERIA)
    type_id = submission_type.pk if submission_type else None
    version = (
        EvaluationGrid.objects.filter(edition=edition, submission_type_id=type_id).aggregate(
            Max("version")
        )["version__max"]
        or 0
    ) + 1
    grid = EvaluationGrid.objects.create(
        edition=edition,
        submission_type=submission_type,
        version=version,
        name=name.strip()[:150],
        scale_min=scale_min,
        scale_max=scale_max,
        scope_key=_scope_key(edition.pk, type_id, version),
    )
    _write_criteria(grid, cleaned)
    record(
        "grid.created",
        actor=actor,
        edition=edition,
        obj=grid,
        after={**snapshot(grid), "criteria": _criteria_snapshot(grid)},
    )
    return grid


@transaction.atomic
def update_grid(
    grid: EvaluationGrid,
    data: Mapping[str, Any],
    *,
    actor: Actor,
    criteria: Sequence[Mapping[str, Any]] | None = None,
) -> EvaluationGrid:
    """Nom, échelle et critères (liste complète) d'une grille **non verrouillée**."""
    grid = EvaluationGrid.objects.select_for_update().get(pk=grid.pk)
    _writable(grid.edition, actor)
    _check_unlocked(grid)
    before = {**snapshot(grid), "criteria": _criteria_snapshot(grid)}
    for name in GRID_FIELDS:
        if name in data:
            setattr(grid, name, data[name])
    if not str(grid.name).strip():
        raise Invalid(fields={"name": [_("Nom obligatoire.")]})
    _check_scale(grid.scale_min, grid.scale_max)
    grid.save()
    if criteria is not None:
        _write_criteria(grid, clean_criteria(criteria))
    record(
        "grid.updated",
        actor=actor,
        edition=grid.edition,
        obj=grid,
        before=before,
        after={**snapshot(grid), "criteria": _criteria_snapshot(grid)},
    )
    return grid


@transaction.atomic
def duplicate_grid(grid: EvaluationGrid, *, actor: Actor) -> EvaluationGrid:
    """RG-05 : nouvelle version, non verrouillée, avec les mêmes critères."""
    criteria = [
        {name: getattr(c, name) for name in CRITERION_FIELDS}
        for c in grid.criteria.order_by("position", "id")
    ]
    return create_grid(
        grid.edition,
        name=grid.name,
        actor=actor,
        submission_type=grid.submission_type,
        scale_min=grid.scale_min,
        scale_max=grid.scale_max,
        criteria=criteria,
    )


@transaction.atomic
def delete_grid(grid: EvaluationGrid, *, actor: Actor) -> None:
    grid = EvaluationGrid.objects.select_for_update().get(pk=grid.pk)
    _writable(grid.edition, actor)
    _check_unlocked(grid)
    record("grid.deleted", actor=actor, edition=grid.edition, obj=grid, before=snapshot(grid))
    grid.delete()


def lock_grid(grid: EvaluationGrid) -> None:
    """Verrou posé à la première évaluation enregistrée (appelé dans sa transaction)."""
    if grid.locked_at is None:
        EvaluationGrid.objects.filter(pk=grid.pk, locked_at__isnull=True).update(
            locked_at=timezone.now()
        )
        grid.refresh_from_db(fields=["locked_at"])


def grid_for(edition: Edition, submission_type: SubmissionType | None) -> EvaluationGrid | None:
    """Grille applicable : dernière version de la grille du type, sinon de la grille « toutes »."""
    grids = EvaluationGrid.objects.filter(edition=edition)
    if submission_type is not None:
        specific = grids.filter(submission_type=submission_type).order_by("-version").first()
        if specific is not None:
            return specific
    return grids.filter(Q(submission_type__isnull=True)).order_by("-version").first()
