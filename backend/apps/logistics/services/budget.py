"""Budget prévisionnel et réalisé (plan L8, N4 ; étude M11, §8.2 ``budget_line``).

- Montants en ``Decimal`` **exacts** dans la devise de l'édition (celle des inscriptions,
  ``apps/core/money.py``) : aucun flottant, aucune conversion.
- Réalisé **calculé**, en lecture seule, pour les lignes dont la source n'est pas
  ``manual`` : « inscriptions » = encaissé net des paiements de L6 ; « partenariats » =
  contributions reçues (L8.3). Chaque source calculée a une ligne par édition, créée à la
  première lecture ; on y saisit le prévu, le libellé et la note, jamais le réalisé.
- Ce n'est pas une comptabilité : ni TVA, ni écriture, ni rapprochement bancaire.
- Journal ``budget.*`` ; exports CSV et XLSX journalisés (RG-17).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import IntegrityError, transaction
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.money import is_exact
from apps.core.private_files import PrivateStore, sniff
from apps.logistics.models import (
    EXPENSE_CATEGORIES,
    BudgetCategory,
    BudgetKind,
    BudgetLine,
    BudgetSource,
)
from apps.registrations.services.settings import registration_settings

ZERO = Decimal(0)
PROOFS = PrivateStore("budget-proofs")
PROOF_MAX_BYTES = 5 * 1024 * 1024
NOTE_MAX_LENGTH = 2000
WRITABLE_FIELDS = frozenset({"kind", "category", "label", "planned", "actual", "note", "position"})


def _registrations_actual(edition: Edition) -> Decimal:
    from apps.payments.services.finance import net_collected

    return net_collected(edition)


# Sources calculées : (nature, poste, libellé par défaut, calcul du réalisé). Les
# partenariats s'ajoutent en L8.3 (``register_computed_source``).
COMPUTED: dict[str, tuple[str, str, Any, Callable[[Edition], Decimal]]] = {
    BudgetSource.REGISTRATIONS: (
        BudgetKind.INCOME,
        BudgetCategory.REGISTRATIONS,
        _("Inscriptions (encaissé net)"),
        _registrations_actual,
    ),
}


def register_computed_source(
    source: str, kind: str, category: str, label: Any, compute: Callable[[Edition], Decimal]
) -> None:
    COMPUTED[source] = (kind, category, label, compute)


def currency(edition: Edition) -> str:
    return registration_settings(edition).currency


def ensure_computed_lines(edition: Edition) -> None:
    """Crée les lignes calculées manquantes (une par source et par édition)."""
    existing = set(
        BudgetLine.objects.filter(edition=edition)
        .exclude(source=BudgetSource.MANUAL)
        .values_list("source", flat=True)
    )
    for source, (kind, category, label, _compute) in COMPUTED.items():
        if source in existing:
            continue
        try:
            with transaction.atomic():
                BudgetLine.objects.create(
                    edition=edition,
                    kind=kind,
                    category=category,
                    label=gettext(label),
                    source=source,
                    computed_key=f"{edition.pk}:{source}",
                    position=1000,
                )
        except IntegrityError:
            pass  # créée entre-temps par une autre requête


def actual_of(line: BudgetLine, cache: dict[str, Decimal] | None = None) -> Decimal | None:
    """Réalisé d'une ligne : saisi, ou calculé pour une source calculée."""
    if line.source == BudgetSource.MANUAL:
        return line.actual
    entry = COMPUTED.get(line.source)
    if entry is None:
        return None
    if cache is not None and line.source in cache:
        return cache[line.source]
    value = entry[3](line.edition)
    if cache is not None:
        cache[line.source] = value
    return value


def lines(edition: Edition) -> list[tuple[BudgetLine, Decimal | None]]:
    ensure_computed_lines(edition)
    cache: dict[str, Decimal] = {}
    rows = BudgetLine.objects.filter(edition=edition).select_related("edition")
    return [(line, actual_of(line, cache)) for line in rows.order_by("kind", "position", "id")]


def summary(edition: Edition) -> dict[str, Any]:
    """Totaux prévu et réalisé par nature et par poste ; solde (recettes moins dépenses)."""
    totals = {
        kind: {"planned": ZERO, "actual": ZERO} for kind in (BudgetKind.EXPENSE, BudgetKind.INCOME)
    }
    by_category: dict[str, dict[str, Any]] = {}
    for line, actual in lines(edition):
        totals[line.kind]["planned"] += line.planned
        totals[line.kind]["actual"] += actual or ZERO
        bucket = by_category.setdefault(
            line.category, {"kind": line.kind, "planned": ZERO, "actual": ZERO}
        )
        bucket["planned"] += line.planned
        bucket["actual"] += actual or ZERO
    expense, income = totals[BudgetKind.EXPENSE], totals[BudgetKind.INCOME]
    return {
        "currency": currency(edition),
        "expense": expense,
        "income": income,
        "balance_planned": income["planned"] - expense["planned"],
        "balance_actual": income["actual"] - expense["actual"],
        "by_category": [
            {"category": category, **values}
            for category, values in sorted(
                by_category.items(),
                key=lambda item: list(BudgetCategory.values).index(item[0]),
            )
        ],
    }


def _amount(edition: Edition, name: str, value: Any, errors: dict) -> Decimal | None:
    if value is None:
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors[name] = [_("Montant attendu.")]
        return None
    if not amount.is_finite() or amount < 0:
        errors[name] = [_("Montant positif ou nul attendu.")]
    elif amount >= Decimal("1e10"):
        errors[name] = [_("Montant trop élevé.")]
    elif not is_exact(amount, currency(edition)):
        errors[name] = [
            _("Trop de décimales pour la devise %(currency)s.") % {"currency": currency(edition)}
        ]
    return amount


def _clean(edition: Edition, data: Mapping[str, Any], *, line: BudgetLine | None) -> dict[str, Any]:
    unknown = set(data) - WRITABLE_FIELDS
    computed = line is not None and line.source != BudgetSource.MANUAL
    if computed:
        # Ligne calculée : nature, poste et réalisé sont fixés par sa source.
        unknown |= {"kind", "category", "actual"} & set(data)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    errors: dict[str, list] = {}
    clean: dict[str, Any] = {}
    if "label" in data or line is None:
        label = (data.get("label") or "").strip()
        if not label:
            errors["label"] = [_("Libellé obligatoire.")]
        elif len(label) > 200:
            errors["label"] = [_("200 caractères au plus.")]
        clean["label"] = label
    if "note" in data:
        note = (data["note"] or "").strip()
        if len(note) > NOTE_MAX_LENGTH:
            errors["note"] = [_("2 000 caractères au plus.")]
        clean["note"] = note
    for name in ("planned", "actual"):
        if name in data:
            clean[name] = _amount(edition, name, data[name], errors)
    if clean.get("planned", ZERO) is None:
        errors["planned"] = [_("Montant attendu.")]
    if "position" in data:
        position = data["position"]
        if not isinstance(position, int) or isinstance(position, bool) or position < 0:
            errors["position"] = [_("Position positive ou nulle attendue.")]
        clean["position"] = position
    kind = data.get("kind", line.kind if line else None)
    category = data.get("category", line.category if line else None)
    if not computed:
        if kind not in BudgetKind.values:
            errors["kind"] = [_("Nature inconnue.")]
        elif category not in BudgetCategory.values:
            errors["category"] = [_("Poste inconnu.")]
        elif (category in EXPENSE_CATEGORIES) != (kind == BudgetKind.EXPENSE):
            errors["category"] = [_("Poste d'une autre nature.")]
        clean["kind"], clean["category"] = kind, category
    if errors:
        raise Invalid(fields=errors)
    return clean


def _snapshot(line: BudgetLine) -> dict[str, Any]:
    values = {name: getattr(line, name) for name in BudgetLine.AUDIT_FIELDS}
    for name in ("planned", "actual"):
        if values[name] is not None:
            values[name] = str(values[name])
    return values


@transaction.atomic
def create_line(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> BudgetLine:
    ensure_editable(edition)
    clean = _clean(edition, data, line=None)
    line = BudgetLine.objects.create(edition=edition, source=BudgetSource.MANUAL, **clean)
    record("budget.line_created", actor=actor, edition=edition, obj=line, after=_snapshot(line))
    return line


@transaction.atomic
def update_line(line: BudgetLine, data: Mapping[str, Any], *, actor: Actor) -> BudgetLine:
    ensure_editable(line.edition)
    line = BudgetLine.objects.select_for_update().select_related("edition").get(pk=line.pk)
    clean = _clean(line.edition, data, line=line)
    before = _snapshot(line)
    for name, value in clean.items():
        setattr(line, name, value)
    line.save()
    after = _snapshot(line)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "budget.line_updated",
            actor=actor,
            edition=line.edition,
            obj=line,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return line


@transaction.atomic
def delete_line(line: BudgetLine, *, actor: Actor) -> None:
    ensure_editable(line.edition)
    if line.source != BudgetSource.MANUAL:
        raise Invalid(fields={"line": [_("Ligne calculée : elle ne se supprime pas.")]})
    if line.proof_storage_name:
        PROOFS.remove_after_commit(line.proof_storage_name)
    record(
        "budget.line_deleted", actor=actor, edition=line.edition, obj=line, before=_snapshot(line)
    )
    line.delete()


@transaction.atomic
def upload_proof(line: BudgetLine, *, data: bytes, name: str, actor: Actor) -> BudgetLine:
    """Justificatif facultatif : PDF, JPEG ou PNG de 5 Mo au plus, type vérifié par contenu,
    stocké hors racine web (règle n° 8). Remplace le précédent."""
    ensure_editable(line.edition)
    line = BudgetLine.objects.select_for_update().select_related("edition").get(pk=line.pk)
    if len(data) > PROOF_MAX_BYTES:
        raise Invalid(fields={"file": [_("Fichier de 5 Mo au plus.")]})
    kind = sniff(data)
    if kind is None:
        raise Invalid(fields={"file": [_("PDF, JPEG ou PNG attendu.")]})
    previous = line.proof_storage_name
    line.proof_storage_name, _digest = PROOFS.write(data)
    line.proof_name = (name or "justificatif").replace("/", "_").replace("\\", "_")[:255]
    line.proof_kind = kind
    line.proof_size = len(data)
    line.save(
        update_fields=["proof_storage_name", "proof_name", "proof_kind", "proof_size", "updated_at"]
    )
    if previous:
        PROOFS.remove_after_commit(previous)
    record(
        "budget.proof_uploaded",
        actor=actor,
        edition=line.edition,
        obj=line,
        after={"kind": kind, "size": len(data)},
    )
    return line


@transaction.atomic
def remove_proof(line: BudgetLine, *, actor: Actor) -> BudgetLine:
    ensure_editable(line.edition)
    line = BudgetLine.objects.select_for_update().select_related("edition").get(pk=line.pk)
    if line.proof_storage_name:
        PROOFS.remove_after_commit(line.proof_storage_name)
        line.proof_storage_name = line.proof_name = line.proof_kind = ""
        line.proof_size = None
        line.save(
            update_fields=[
                "proof_storage_name",
                "proof_name",
                "proof_kind",
                "proof_size",
                "updated_at",
            ]
        )
        record("budget.proof_removed", actor=actor, edition=line.edition, obj=line)
    return line


def known_proofs() -> list[str]:
    return list(
        BudgetLine.objects.exclude(proof_storage_name="").values_list(
            "proof_storage_name", flat=True
        )
    )


def export_rows(edition: Edition) -> tuple[list[str], list[list[Any]]]:
    """En-tête et lignes de l'export (CSV et XLSX), dans la langue de la requête."""
    header = [
        gettext("Nature"),
        gettext("Poste"),
        gettext("Libellé"),
        gettext("Prévu"),
        gettext("Réalisé"),
        gettext("Écart"),
        gettext("Origine du réalisé"),
        gettext("Note"),
        gettext("Devise"),
    ]
    unit = currency(edition)
    rows = []
    for line, actual in lines(edition):
        rows.append(
            [
                str(BudgetKind(line.kind).label),
                str(BudgetCategory(line.category).label),
                line.label,
                line.planned,
                "" if actual is None else actual,
                "" if actual is None else actual - line.planned,
                str(BudgetSource(line.source).label),
                line.note,
                unit,
            ]
        )
    return header, rows


def record_export(edition: Edition, *, actor: Actor, file_format: str, count: int) -> None:
    record(
        "budget.exported",
        actor=actor,
        edition=edition,
        after={"format": file_format, "rows": count},
    )
