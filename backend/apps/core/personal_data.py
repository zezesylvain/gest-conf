"""Registre des données personnelles (plan L1 §4.9, RG-18, D15).

Chaque application déclare, dans ``AppConfig.ready()``, les modèles qui portent des
données d'un compte, et deux fonctions :

- ``export(user) -> dict`` : sa section de l'export (« Mes données ») ;
- ``anonymize(user, context)`` : son effacement, dans la transaction d'anonymisation.

Le test d'introspection (``tests/test_personal_data.py``) échoue si un modèle ayant une
clé étrangère vers ``User`` ou un ``EmailField`` n'est ni déclaré ici, ni exempté avec une
justification : chaque lot futur doit traiter les données qu'il ajoute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from apps.core.actor import Actor


@dataclass(frozen=True, slots=True)
class AnonymizationContext:
    """Données d'origine, lues **avant** tout effacement (les traitements s'exécutent
    ensuite dans l'ordre de leur rang)."""

    actor: Actor
    anonymized_email: str
    original_emails: frozenset[str]
    names: frozenset[str] = field(default_factory=frozenset)


type ExportFunction = Callable[[Any], dict[str, Any]]
type AnonymizeFunction = Callable[[Any, AnonymizationContext], None]


@dataclass(frozen=True, slots=True)
class PersonalDataHandler:
    name: str
    models: tuple[str, ...]
    export: ExportFunction | None
    anonymize: AnonymizeFunction | None
    rank: int


_HANDLERS: dict[str, PersonalDataHandler] = {}
_EXEMPTIONS: dict[str, str] = {}


def register_personal_data(
    name: str,
    *,
    models: tuple[str, ...],
    export: ExportFunction | None = None,
    anonymize: AnonymizeFunction | None = None,
    rank: int = 100,
) -> None:
    """Déclare un traitement. ``models`` : libellés ``app_label.Model`` couverts.
    ``rank`` : ordre d'anonymisation (le compte lui-même passe en dernier)."""
    existing = _HANDLERS.get(name)
    if existing is not None and existing.export is not export:
        raise ValueError(f"Traitement de données personnelles déjà enregistré : {name}")
    _HANDLERS[name] = PersonalDataHandler(name, models, export, anonymize, rank)


def exempt_model(label: str, justification: str) -> None:
    """Modèle sans donnée personnelle propre, malgré sa clé vers ``User`` (justifié)."""
    if not justification.strip():
        raise ValueError("Justification obligatoire.")
    _EXEMPTIONS[label] = justification


def handlers() -> list[PersonalDataHandler]:
    return sorted(_HANDLERS.values(), key=lambda handler: (handler.rank, handler.name))


def covered_models() -> set[str]:
    return {label for handler in _HANDLERS.values() for label in handler.models}


def exemptions() -> dict[str, str]:
    return dict(_EXEMPTIONS)


def export_sections(user: Any) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for handler in handlers():
        if handler.export is not None:
            sections.update(handler.export(user))
    return sections


def anonymize_sections(user: Any, context: AnonymizationContext) -> None:
    for handler in handlers():
        if handler.anonymize is not None:
            handler.anonymize(user, context)
