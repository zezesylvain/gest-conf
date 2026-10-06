"""RG-04 (double aveugle) : ce qu'un relecteur ne reçoit jamais (plan L4, H9 ; règle n° 3).

Trois garde-fous, posés avant le premier endpoint relecteur :

1. **Registre** des champs d'identité (``IDENTITY_FIELDS``), par modèle : compte, profil,
   adresses, auteurs, soumissionnaire, métadonnées du fichier (nom d'origine, taille,
   empreinte), révisions (clichés avec auteurs), historique et dérogations.
2. **Liste blanche** : tout sérialiseur servi à un relecteur dérive de ``ReviewerSerializer``
   ou de ``ReviewerModelSerializer`` et déclare ses champs un à un. ``identity_violations``
   (méta-test) refuse un champ, même imbriqué ou atteint par ``source``, qui mène à un champ
   du registre, un champ calculé non justifié et ``exclude`` ; les champs sont énumérés.
3. **Test de fuite** : ``find_identity_leaks`` cherche, dans toute réponse d'un endpoint
   relecteur, des valeurs traceuses (noms, adresses, institutions, nom de fichier) et des clés
   d'identité.

Le registre vaut pour les éditions en double aveugle ; sans double aveugle (Q3), le serveur
choisit un autre sérialiseur, avec auteurs, et le documente à son endroit.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Any, ClassVar

from django.apps import apps
from django.db import models
from rest_framework import serializers

# Tous les champs du modèle sont des données d'identité.
ALL = "*"

IDENTITY_FIELDS: Mapping[str, frozenset[str] | str] = {
    "accounts.User": ALL,
    "accounts.Profile": ALL,
    "account.EmailAddress": ALL,
    "submissions.SubmissionAuthor": ALL,
    "submissions.SubmissionRevision": ALL,  # clichés : auteurs compris
    "submissions.StatusHistory": ALL,  # acteur et motifs (retrait)
    "submissions.SubmissionExtension": ALL,  # motif, auteur de la dérogation
    "submissions.Submission": frozenset(
        {
            "submitter",
            "authors",
            "revisions",
            "status_history",
            "extensions",
            "reminders",
            "withdraw_reason",
            "declarations",
            "title_key",
        }
    ),
    "submissions.SubmissionFile": frozenset(
        {"original_name", "storage_name", "size", "sha256", "uploaded_by"}
    ),
}

# Clés de réponse qui trahissent une identité, quelle que soit la valeur (test de fuite).
IDENTITY_KEYS: frozenset[str] = frozenset(
    {
        "email",
        "first_name",
        "last_name",
        "institution",
        "affiliation",
        "authors",
        "submitter",
        "submitter_name",
        "original_name",
        "orcid",
    }
)


class ReviewerSerializerMixin:
    """Marque un sérialiseur servi à un relecteur (liste blanche, contrôlée par le méta-test).

    ``reviewer_computed`` : champs calculés autorisés, nom → justification. Un
    ``SerializerMethodField`` absent de ce dictionnaire est refusé : ce qu'il renvoie
    échappe au contrôle des champs, seul le test de fuite le verrait.
    """

    reviewer_computed: ClassVar[Mapping[str, str]] = {}
    # Sérialiseur sans modèle : modèle dont les champs sont lus (résolution des ``source``).
    reviewer_model: ClassVar[str | None] = None


_REGISTRY: list[type[serializers.BaseSerializer]] = []


def reviewer_serializers() -> list[type[serializers.BaseSerializer]]:
    """Sérialiseurs relecteur déclarés (importés par leurs modules)."""
    return list(_REGISTRY)


class ReviewerSerializer(ReviewerSerializerMixin, serializers.Serializer):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _REGISTRY.append(cls)


class ReviewerModelSerializer(ReviewerSerializerMixin, serializers.ModelSerializer):
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _REGISTRY.append(cls)


def _label(model: type[models.Model]) -> str:
    return model._meta.label


def _is_identity(model: type[models.Model], name: str) -> bool:
    entry = IDENTITY_FIELDS.get(_label(model))
    return entry == ALL or (entry is not None and entry != ALL and name in entry)


def _related_model(model: type[models.Model], name: str) -> type[models.Model] | None:
    try:
        field = model._meta.get_field(name)
    except Exception:  # attribut ou propriété : pas de relation à suivre
        return None
    return field.related_model if field.is_relation else None


def _check_source(model: type[models.Model] | None, source: str, where: str) -> list[str]:
    """Chemin ``a.b.c`` lu depuis ``model`` : refus dès qu'un maillon est un champ d'identité."""
    problems: list[str] = []
    current = model
    for part in source.split("."):
        if current is None:
            break
        if _is_identity(current, part):
            problems.append(f"{where} : {_label(current)}.{part} est une donnée d'identité")
            break
        current = _related_model(current, part)
    return problems


def _model_of(serializer: serializers.BaseSerializer) -> type[models.Model] | None:
    meta = getattr(serializer, "Meta", None)
    model = getattr(meta, "model", None)
    if model is not None:
        return model
    label = getattr(serializer, "reviewer_model", None)
    return apps.get_model(label) if label else None


def identity_violations(serializer_class: type[serializers.BaseSerializer]) -> list[str]:
    """Problèmes RG-04 d'un sérialiseur relecteur (vide : conforme)."""
    name = serializer_class.__name__
    problems: list[str] = []
    meta = getattr(serializer_class, "Meta", None)
    if meta is not None and getattr(meta, "exclude", None) is not None:
        problems.append(f"{name} : « exclude » interdit (liste blanche)")
    # Champs énumérés un à un (le raccourci « tous les champs » est déjà refusé partout par
    # tests/test_platform_rules.py).
    if (
        meta is not None
        and getattr(meta, "exclude", None) is None
        and hasattr(meta, "model")
        and not isinstance(getattr(meta, "fields", None), list | tuple)
    ):
        problems.append(f"{name} : « Meta.fields » doit énumérer les champs")
    if problems:
        return problems
    serializer = serializer_class()
    model = _model_of(serializer)
    computed = getattr(serializer_class, "reviewer_computed", {})
    for field_name, field in serializer.fields.items():
        where = f"{name}.{field_name}"
        if isinstance(field, serializers.SerializerMethodField):
            if not str(computed.get(field_name, "")).strip():
                problems.append(f"{where} : champ calculé sans justification (reviewer_computed)")
            continue
        nested = field.child if isinstance(field, serializers.ListSerializer) else field
        if isinstance(nested, serializers.BaseSerializer):
            if type(nested) not in _REGISTRY:
                problems.append(f"{where} : sérialiseur imbriqué hors liste blanche relecteur")
            if field.source != "*":
                problems += _check_source(model, field.source, where)
            continue
        if field.source != "*":
            problems += _check_source(model, field.source, where)
    return problems


def _walk(value: Any, path: str = "$") -> Iterator[tuple[str, str | None, Any]]:
    """Parcourt une réponse JSON : (chemin, clé, valeur) pour chaque nœud."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield f"{path}.{key}", str(key), item
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield f"{path}[{index}]", None, item
            yield from _walk(item, f"{path}[{index}]")


def find_identity_leaks(payload: Any, tracers: Iterable[str]) -> list[str]:
    """Test de fuite RG-04 : chemins où apparaît une clé d'identité ou une valeur traceuse
    (comparaison sans casse, sur toute chaîne, y compris imbriquée). Vide : aucune fuite."""
    needles = [tracer.casefold() for tracer in tracers if tracer]
    leaks: list[str] = []
    for path, key, value in _walk(payload):
        if key is not None and key in IDENTITY_KEYS:
            leaks.append(f"{path} : clé d'identité « {key} »")
        if isinstance(value, str):
            text = value.casefold()
            leaks += [f"{path} : traceur « {n} »" for n in needles if n in text]
    return leaks
