"""Journal d'audit : écriture des entrées (RG-17, plan L1 §7.2).

- ``record`` est appelé **dans la transaction du service métier** : si l'action est
  annulée, aucune trace ne subsiste, et inversement (``AuditLog`` est une table
  ordinaire, sans connexion ni transaction propre).
- ``snapshot`` ne retient que les champs déclarés dans ``AUDIT_FIELDS`` par le modèle
  (liste blanche) : jamais d'adresse e-mail en clair (un champ calculé masqué, par
  exemple ``email_masked``, la remplace), de mot de passe, de secret ni de jeton.
- ``record`` refuse en dernier rempart, dans ``before`` et ``after`` : les clés
  ``password``, ``secret`` et ``token`` (égalité stricte) et toute valeur contenant une
  adresse e-mail non masquée (analyse récursive des valeurs, plan §7.5).
- Les actions forment un catalogue fermé (``AuditAction``) : une action n'y entre
  qu'avec le code qui l'émet, comme les codes d'erreur (``ErrorCode``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from apps.core.actor import USER_AGENT_MAX_LENGTH, Actor, ActorKind
from apps.core.models import AuditLog


class AuditAction(StrEnum):
    """Catalogue des actions journalisées (code ``domaine.verbe``, plan L1 §7.3)."""

    # Conservation des données (D15) : méthodes nommées d'AuditLog et commande cleanup.
    AUDIT_PURGED = "audit.purged"
    AUDIT_NETWORK_PURGED = "audit.network_purged"
    AUDIT_NETWORK_REDACTED = "audit.network_redacted"
    RETENTION_APPLIED = "retention.applied"
    # Commandes d'opérateur (actor_kind=command).
    COMMAND_SEND_TEST_EMAIL = "command.send_test_email"
    COMMAND_OUTBOX_RETRY = "command.outbox_retry"


# Actions sensibles : motif obligatoire (plan L1 §3.5, « commandes sensibles »). Le renvoi
# d'un e-mail en échec agit sur la correspondance d'un tiers.
REASON_REQUIRED_ACTIONS: frozenset[AuditAction] = frozenset({AuditAction.COMMAND_OUTBOX_RETRY})

# Noms de clés interdits dans before/after, à tout niveau (égalité stricte, plan §7.5).
FORBIDDEN_KEYS: frozenset[str] = frozenset({"password", "secret", "token"})

# Adresse e-mail en clair : une suite de caractères ni « * » ni blancs, suivie de « @ ».
# Le format masqué « j***@univ.ci » n'y répond pas (le caractère qui précède « @ » est « * »).
CLEAR_EMAIL_PATTERN = re.compile(r"[^*\s]+@")

OBJECT_FIELD_MAX_LENGTH = 64
REQUEST_ID_MAX_LENGTH = 32


def mask_email(address: str) -> str:
    """``jean.dupont@univ.ci`` → ``j***@univ.ci`` (forme admise dans le journal et à l'écran)."""
    local, separator, domain = address.strip().rpartition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"


def contains_clear_email(value: Any) -> bool:
    """Vrai si une chaîne, à n'importe quel niveau de ``value``, contient une adresse en clair."""
    if isinstance(value, str):
        return CLEAR_EMAIL_PATTERN.search(value) is not None
    if isinstance(value, Mapping):
        return any(contains_clear_email(item) for item in value.values())
    if isinstance(value, list | tuple):
        return any(contains_clear_email(item) for item in value)
    return False


def _forbidden_keys(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        found = {key for key in value if str(key).lower() in FORBIDDEN_KEYS}
        for item in value.values():
            found |= _forbidden_keys(item)
        return found
    if isinstance(value, list | tuple):
        return set().union(*(_forbidden_keys(item) for item in value)) if value else set()
    return set()


def _to_json(data: Mapping[str, Any]) -> dict[str, Any]:
    """Valeurs JSON natives (dates en ISO 8601, décimaux en chaînes), comme en base."""
    return json.loads(json.dumps(dict(data), cls=DjangoJSONEncoder))


def _clean_state(state: Mapping[str, Any] | None, name: str) -> dict[str, Any] | None:
    if state is None:
        return None
    if not isinstance(state, Mapping):
        raise TypeError(f"{name} doit être un dictionnaire ou None.")
    cleaned = _to_json(state)
    forbidden = _forbidden_keys(cleaned)
    if forbidden:
        raise ValueError(f"Clés interdites dans {name} : {sorted(forbidden)}")
    if contains_clear_email(cleaned):
        raise ValueError(
            f"Adresse e-mail en clair dans {name} : journaliser un champ masqué (mask_email)."
        )
    return cleaned


def snapshot(instance: models.Model) -> dict[str, Any]:
    """État d'``instance`` réduit aux champs ``AUDIT_FIELDS`` de son modèle (liste blanche).

    Un nom peut désigner un champ du modèle (clé étrangère : son identifiant) ou un
    attribut calculé (par exemple ``email_masked``). Un champ ``EmailField`` est refusé.
    """
    model = type(instance)
    names = getattr(model, "AUDIT_FIELDS", None)
    if not names:
        raise ImproperlyConfigured(f"{model._meta.label} ne déclare pas AUDIT_FIELDS.")
    data: dict[str, Any] = {}
    for name in names:
        if name.lower() in FORBIDDEN_KEYS:
            raise ImproperlyConfigured(f"{model._meta.label}.AUDIT_FIELDS contient {name!r}.")
        try:
            field = model._meta.get_field(name)
        except FieldDoesNotExist:
            data[name] = getattr(instance, name)
            continue
        if isinstance(field, models.EmailField):
            raise ImproperlyConfigured(
                f"{model._meta.label}.{name} : adresse e-mail en clair interdite dans "
                "AUDIT_FIELDS (journaliser un champ masqué)."
            )
        data[name] = field.value_from_object(instance)
    return _to_json(data)


def record(
    action: AuditAction | str,
    *,
    actor: Actor,
    obj: models.Model | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str = "",
) -> AuditLog:
    """Écrit une entrée du journal, dans la transaction de l'appelant.

    Lève ``ValueError`` pour une action hors catalogue, un motif manquant sur une action
    sensible, une clé interdite ou une adresse en clair dans ``before``/``after``.
    """
    action = AuditAction(action)
    reason = reason.strip()
    if action in REASON_REQUIRED_ACTIONS and not reason:
        raise ValueError(f"Motif obligatoire pour l'action {action.value}.")
    object_type = object_id = ""
    if obj is not None:
        if obj.pk is None:
            raise ValueError("L'objet journalisé doit être enregistré (clé primaire connue).")
        object_type = obj._meta.label_lower[:OBJECT_FIELD_MAX_LENGTH]
        object_id = str(obj.pk)[:OBJECT_FIELD_MAX_LENGTH]
    entry = AuditLog(
        at=timezone.now(),
        actor=actor.user if actor.kind == ActorKind.USER else None,
        actor_kind=actor.kind,
        actor_label=actor.label,
        action=action.value,
        object_type=object_type,
        object_id=object_id,
        before=_clean_state(before, "before"),
        after=_clean_state(after, "after"),
        reason=reason,
        request_id=actor.request_id[:REQUEST_ID_MAX_LENGTH],
        ip=actor.ip,
        user_agent=actor.user_agent[:USER_AGENT_MAX_LENGTH],
    )
    entry.save()
    return entry
