"""Calcul des notes (plan L4, H4 ; étude §5.1 et annexe A4). Toujours par le serveur, en
``Decimal`` : une note envoyée par le client est ignorée.

Note pondérée d'une évaluation, ramenée sur 100 :
``(Σ poids_i * note_i / Σ poids_i - min) / (max - min) * 100``, sur les critères notés ;
un critère facultatif non noté est exclu (poids renormalisés), un critère obligatoire non noté
rend la note indéfinie. Arrondi à 2 décimales, au plus proche, demi supérieur.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class CriterionWeight:
    key: int | str
    weight: Decimal
    required: bool = True


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def weighted_score(
    criteria: Sequence[CriterionWeight],
    values: Mapping[int | str, Decimal],
    scale_min: Decimal | int,
    scale_max: Decimal | int,
) -> Decimal | None:
    """Note sur 100 d'une évaluation ; ``None`` si un critère obligatoire n'est pas noté ou si
    aucun critère ne l'est."""
    low, high = Decimal(scale_min), Decimal(scale_max)
    if any(c.required and c.key not in values for c in criteria):
        return None
    scored = [(c.weight, Decimal(values[c.key])) for c in criteria if c.key in values]
    total = sum((weight for weight, _value in scored), Decimal(0))
    if not scored or total <= 0:
        return None
    mean = sum((weight * value for weight, value in scored), Decimal(0)) / total
    return quantize((mean - low) / (high - low) * HUNDRED)


def final_score(
    reviews: Iterable[tuple[Decimal, int | None]], *, confidence_weighted: bool = False
) -> Decimal | None:
    """Score final d'une soumission : moyenne des notes des évaluations envoyées ; option de
    l'édition, moyenne pondérée par la confiance (1 à 5, une confiance absente vaut 1)."""
    rows = [(Decimal(score), confidence or 1) for score, confidence in reviews]
    if not rows:
        return None
    if confidence_weighted:
        weight = sum(confidence for _score, confidence in rows)
        return quantize(sum(score * confidence for score, confidence in rows) / weight)
    return quantize(sum(score for score, _confidence in rows) / len(rows))


def divergence(scores: Iterable[Decimal]) -> Decimal:
    """Écart maximal entre les notes pondérées des évaluations envoyées (H12)."""
    values = list(scores)
    return quantize(max(values) - min(values)) if len(values) > 1 else Decimal("0.00")
