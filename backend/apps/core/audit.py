"""Journal d'audit (RG-17, plan L1 §7.2).

``record`` est appelé **dans la transaction du service métier** : si l'action est
annulée, aucune trace ne subsiste, et inversement. ``snapshot`` ne reprend que
les champs déclarés dans ``AUDIT_FIELDS`` par le modèle (liste blanche).

Garde-fous appliqués à chaque écriture, et non seulement par les tests :

- aucune clé interdite (``password``, ``secret``, ``token``...) dans ``before`` ou
  ``after``, à quelque profondeur que ce soit ;
- aucune adresse e-mail en clair dans leurs valeurs : seule la forme masquée
  ``x***@domaine`` (``mask_email``) est acceptée, car le journal survit à
  l'anonymisation du compte (plan §4.9, D15).
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.utils import timezone

from apps.core.actor import Actor, ActorKind
from apps.core.models import AuditLog

if TYPE_CHECKING:
    from django.db.models import Model

ACTION_MAX_LENGTH = 64
ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# Noms de clés interdits dans before/after (égalité stricte, insensible à la casse).
# « email » n'y figure pas : « email_masked » et une valeur masquée sont légitimes,
# et les valeurs sont contrôlées séparément (CLEAR_EMAIL_PATTERN).
FORBIDDEN_KEYS = frozenset({"password", "secret", "token", "key", "otp", "totp_secret"})

# Adresse en clair : un caractère autre que « * » juste avant « @ ». La forme masquée
# « x***@domaine » (mask_email) ne correspond pas : seul « * » y précède « @ ».
CLEAR_EMAIL_PATTERN = re.compile(r"[^*\s@]@")


class AuditDataError(ValueError):
    """Donnée interdite dans un cliché d'audit (secret ou adresse e-mail en clair)."""


# Adresse dans un texte libre : partie locale remplacée par « x*** » (plan L8 : descriptions
# de tâche, notes de budget, présentations de partenaire, que l'on journalise).
_EMAIL_LOCAL_PART = re.compile(r"[^\s@<>\"'(),;:/*]+@")


def mask_emails(value: Any) -> Any:
    """Masque les adresses des textes libres d'une valeur à journaliser (``j***@univ.ci``),
    récursivement dans les dictionnaires et les listes."""
    if isinstance(value, str):
        return _EMAIL_LOCAL_PART.sub(lambda match: f"{match.group(0)[0]}***@", value)
    if isinstance(value, Mapping):
        return {key: mask_emails(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [mask_emails(item) for item in value]
    return value


def mask_email(email: str) -> str:
    """``jeanne.dupont@univ.ci`` → ``j***@univ.ci`` (plan L1 §7.2)."""
    local, sep, domain = email.partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def _jsonable(value: Any, path: str) -> Any:
    """Convertit en valeur JSON et vérifie l'absence de donnée interdite."""
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            key = str(key)
            if key.lower() in FORBIDDEN_KEYS:
                raise AuditDataError(f"Clé interdite dans le journal d'audit : {path}{key}")
            result[key] = _jsonable(item, f"{path}{key}.")
        return result
    if isinstance(value, list | tuple | set | frozenset):
        items = sorted(value, key=str) if isinstance(value, set | frozenset) else value
        return [_jsonable(item, path) for item in items]
    if isinstance(value, str):
        if CLEAR_EMAIL_PATTERN.search(value):
            raise AuditDataError(f"Adresse e-mail en clair dans le journal d'audit : {path}")
        return value
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, Decimal | uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime | dt.date | dt.time):
        return value.isoformat()
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, models.Choices):
        return value.value
    raise AuditDataError(f"Type non journalisable ({type(value).__name__}) : {path}")


def snapshot(instance: Model) -> dict[str, Any]:
    """Cliché des seuls ``AUDIT_FIELDS`` du modèle (liste blanche, plan L1 §7.2).

    Une clé étrangère est journalisée par son identifiant (``<champ>_id``). Un
    modèle sans ``AUDIT_FIELDS`` ne peut pas être photographié : l'oubli est
    détecté à la première utilisation.
    """
    fields = getattr(type(instance), "AUDIT_FIELDS", None)
    if fields is None:
        raise TypeError(f"{type(instance).__name__} ne déclare pas AUDIT_FIELDS.")
    result: dict[str, Any] = {}
    for name in fields:
        try:
            field = instance._meta.get_field(name)
        except FieldDoesNotExist:  # attribut calculé, par exemple « email_masked »
            field = None
        if field is not None and field.is_relation and field.many_to_one:
            result[name] = getattr(instance, field.attname)
        else:
            result[name] = getattr(instance, name)
    return _jsonable(result, "")


def record(
    action: str,
    *,
    actor: Actor,
    edition: Model | None = None,
    obj: Model | None = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    reason: str = "",
) -> AuditLog:
    """Écrit une entrée du journal d'audit (RG-17).

    ``action`` est un code ``domaine.verbe`` (``role.revoked``). ``edition`` rattache
    l'entrée à une édition : seules ces entrées sont visibles par l'API de gestion
    (``GET …/audit``) ; les autres (connexions, comptes) passent par ``audit_query``.
    """
    if len(action) > ACTION_MAX_LENGTH or not ACTION_PATTERN.match(action):
        raise ValueError(f"Code d'action invalide : {action!r} (forme attendue domaine.verbe).")
    if obj is not None and obj.pk is None:
        raise ValueError("L'objet audité doit être enregistré (clé primaire attendue).")
    return AuditLog.objects.create(
        at=timezone.now(),
        actor=actor.user if actor.kind == ActorKind.USER else None,
        actor_kind=actor.kind,
        actor_label=actor.label,
        edition=edition,
        action=action,
        object_type=obj._meta.label_lower if obj is not None else "",
        object_id=str(obj.pk) if obj is not None else "",
        before=_jsonable(before, "before.") if before is not None else None,
        after=_jsonable(after, "after.") if after is not None else None,
        reason=reason,
        request_id=actor.request_id,
        ip=actor.ip,
        user_agent=actor.user_agent,
    )
