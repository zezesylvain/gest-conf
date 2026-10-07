"""Budget propre à une requête HTTP, lisible sans l'objet ``request`` (plan L1 §8.3).

La voie rapide d'envoi des e-mails est plafonnée à ``FAST_PATH_MAX_PER_REQUEST`` envois
pendant une même requête ; les suivants partent au passage du cron. Le compteur est posé
et remis à zéro par ``RequestIdMiddleware`` (``request_scope``).

**Pourquoi une ``ContextVar`` plutôt qu'un attribut de la requête.** Les services ne
reçoivent jamais ``request`` (plan §7.2) : ``queue_email`` est appelé par un service
métier qui ne la connaît pas. Une ``ContextVar`` est propre au fil d'exécution (Passenger
peut servir plusieurs requêtes en parallèle dans des fils distincts) et à la tâche
asynchrone ; elle est restaurée dans un ``finally`` même si la vue lève une exception.
Hors requête (cron, commandes, shell), elle vaut ``None`` : aucune voie rapide, le cron
envoie, ce qui ne retarde aucune réponse HTTP puisqu'il n'y en a pas.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

# Plafond des envois immédiats par requête (plan §8.3, v3) : sans lui, une création de
# 50 invitations ferait 50 allers-retours HTTPS vers le fournisseur pendant la requête.
FAST_PATH_MAX_PER_REQUEST = 3


@dataclass(slots=True)
class _RequestBudget:
    fast_path_remaining: int


_current_budget: ContextVar[_RequestBudget | None] = ContextVar(
    "gestconf_request_budget", default=None
)


@contextmanager
def request_scope(fast_path_limit: int = FAST_PATH_MAX_PER_REQUEST) -> Iterator[None]:
    """Ouvre un budget neuf pour la durée d'une requête (ou d'un test)."""
    token = _current_budget.set(_RequestBudget(fast_path_remaining=fast_path_limit))
    try:
        yield
    finally:
        _current_budget.reset(token)


def take_fast_path_slot() -> bool:
    """Consomme un envoi immédiat du budget de la requête ; ``False`` s'il est épuisé ou absent."""
    budget = _current_budget.get()
    if budget is None or budget.fast_path_remaining <= 0:
        return False
    budget.fast_path_remaining -= 1
    return True


def fast_path_remaining() -> int | None:
    """Envois immédiats encore permis (``None`` hors requête) ; pour les tests et le diagnostic."""
    budget = _current_budget.get()
    return None if budget is None else budget.fast_path_remaining
