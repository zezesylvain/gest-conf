"""Segments de destinataires des envois groupés (plan L8, N1 et N11 ; RG-22 proposée).

Catalogue **fermé**, déclaré par les applications métier dans leur ``ready()``
(``register_segment``), sur le modèle de ``register_guard`` du workflow des soumissions :
``communications`` ne dépend d'aucune d'elles. Un segment renvoie les comptes d'une
édition ; ``recipients`` ne garde que les comptes actifs et non anonymisés, un compte une
seule fois.

Un segment peut exiger une capacité en plus de ``communications.send`` : « relecteurs en
retard » lit l'état des évaluations, réservé à ``reviews.manage`` (le CO n'a aucun accès aux
évaluations, H1 du plan L4).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from django.db.models import QuerySet
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.core.errors import Invalid, NotAllowed

SegmentQuery = Callable[..., QuerySet]


@dataclass(frozen=True)
class Segment:
    """Un segment : ``query(edition)`` renvoie un queryset de comptes (``User``)."""

    code: str
    label: str | Promise
    query: SegmentQuery
    position: int = 100
    capability: str | None = None


_SEGMENTS: dict[str, Segment] = {}


def register_segment(segment: Segment) -> None:
    """Déclare un segment ; une même déclaration répétée est ignorée, un code réutilisé par
    une autre déclaration est une erreur de configuration."""
    known = _SEGMENTS.get(segment.code)
    if known is not None and known != segment:
        raise ValueError(f"Segment déjà déclaré : {segment.code}")
    _SEGMENTS[segment.code] = segment


def all_segments() -> list[Segment]:
    return sorted(_SEGMENTS.values(), key=lambda item: (item.position, item.code))


def available_segments(capabilities: Iterable[str]) -> list[Segment]:
    """Segments utilisables par un détenteur de ``capabilities``."""
    held = set(capabilities)
    return [item for item in all_segments() if item.capability is None or item.capability in held]


def get_segment(code: str, capabilities: Iterable[str]) -> Segment:
    """Segment ``code`` s'il existe et que ``capabilities`` l'autorise ; sinon une erreur."""
    segment = _SEGMENTS.get(code)
    if segment is None:
        raise Invalid(fields={"segment": [_("Segment inconnu.")]})
    if segment.capability is not None and segment.capability not in set(capabilities):
        raise NotAllowed()
    return segment


def recipients(edition, segment: Segment) -> QuerySet[User]:
    """Comptes destinataires : actifs, non anonymisés, chacun une fois, dans un ordre stable."""
    return User.objects.filter(
        pk__in=segment.query(edition).values("pk"),
        is_active=True,
        anonymized_at__isnull=True,
    ).order_by("pk")
