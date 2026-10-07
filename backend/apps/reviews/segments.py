"""Segments des envois groupés : relecteurs (plan L8, N11).

« Relecteurs en retard » lit l'état des évaluations : il est réservé à ``reviews.manage``
(le CO n'a aucun accès aux évaluations, H1 du plan L4).
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.roles import Capability
from apps.reviews.models import AssignmentStatus, ReviewStatus
from apps.reviews.services.assignments import REVIEWABLE


def _active(edition) -> Q:
    return Q(
        review_assignments__submission__edition=edition,
        review_assignments__status=AssignmentStatus.ACTIVE,
    )


def reviewers(edition):
    """Comptes qui ont au moins une affectation active dans l'édition."""
    return User.objects.filter(_active(edition))


def late_reviewers(edition):
    """Évaluation non envoyée, échéance passée, soumission toujours en évaluation."""
    pending = Q(review_assignments__review__isnull=True) | Q(
        review_assignments__review__status=ReviewStatus.DRAFT
    )
    return User.objects.filter(
        _active(edition)
        & pending
        & Q(review_assignments__due_at__lt=timezone.now())
        & Q(review_assignments__submission__status__in=REVIEWABLE)
    )


def register_reviews_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(Segment("reviewers.all", _("Relecteurs"), reviewers, 30))
    register_segment(
        Segment(
            "reviewers.late",
            _("Relecteurs en retard"),
            late_reviewers,
            31,
            Capability.REVIEWS_MANAGE,
        )
    )
