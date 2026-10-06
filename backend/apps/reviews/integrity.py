"""Contrôles d'intégrité de l'évaluation (``check_integrity`` ; plan L4 §3)."""

from __future__ import annotations

from decimal import Decimal

from django.db.models import F, Q, Sum

from apps.reviews.models import AssignmentStatus, EvaluationGrid, Review, ReviewAssignment
from apps.reviews.services.scoring import CriterionWeight, weighted_score


def check_grid_weights() -> list[str]:
    """RG-05 : chaque grille pèse exactement 100."""
    problems = []
    for grid in EvaluationGrid.objects.annotate(total=Sum("criteria__weight")):
        # Somme normalisée à deux décimales (SQLite et MariaDB ne la rendent pas pareil).
        total = Decimal(grid.total or 0).quantize(Decimal("0.01"))
        if total != Decimal("100"):
            problems.append(f"grille {grid.pk} : somme des poids {total}")
    return problems


def review_score(review: Review) -> Decimal | None:
    """Note recalculée à partir des notes stockées (même calcul que le service)."""
    grid = review.grid
    criteria = [
        CriterionWeight(key=c.pk, weight=c.weight, required=c.is_required)
        for c in grid.criteria.all()
    ]
    values = {score.criterion_id: score.value for score in review.scores.all()}
    return weighted_score(criteria, values, grid.scale_min, grid.scale_max)


def check_review_scores() -> list[str]:
    """H4 : la note stockée est celle que le serveur recalcule."""
    problems = []
    reviews = Review.objects.select_related("grid").prefetch_related("grid__criteria", "scores")
    for review in reviews:
        if review.weighted_score is not None and review_score(review) != review.weighted_score:
            problems.append(f"évaluation {review.pk} : note stockée différente du calcul")
    return problems


def check_assignments() -> list[str]:
    """H6, H8 : clé active renseignée si et seulement si l'affectation est active ; aucune
    affectation active d'un relecteur auteur de la soumission (conflit jamais levable)."""
    problems = []
    inconsistent = ReviewAssignment.objects.filter(
        Q(status=AssignmentStatus.ACTIVE, active_key__isnull=True)
        | (~Q(status=AssignmentStatus.ACTIVE) & Q(active_key__isnull=False))
    )
    for pk in inconsistent.values_list("pk", flat=True):
        problems.append(f"affectation {pk} : clé active incohérente avec le statut")
    author = ReviewAssignment.objects.filter(status=AssignmentStatus.ACTIVE).filter(
        Q(reviewer=F("submission__submitter")) | Q(submission__authors__user=F("reviewer"))
    )
    for pk in author.values_list("pk", flat=True).distinct():
        problems.append(f"affectation {pk} : le relecteur est auteur de la soumission")
    return problems
