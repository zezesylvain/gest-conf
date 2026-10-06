"""Paramètres du programme de l'édition (plan L5, I17)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import Invalid

SETTINGS_FIELDS = ("session_buffer_minutes", "presenter_registration_required")


def _writable(edition: Edition, actor: Actor) -> None:
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(edition)


@transaction.atomic
def update_program_settings(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Edition:
    """Tampon entre créneaux (RG-13, 0 à 30 minutes) et RG-11 (désactivable ; sans effet
    avant L6). Journalisé avec l'avant et l'après (RG-17).

    Un changement de tampon déplace les créneaux de toutes les sessions : ils sont recalculés
    sous le verrou de la planification, et la révision du brouillon change (I14)."""
    from apps.program.models import Session
    from apps.program.services import planning

    unknown = set(data) - set(SETTINGS_FIELDS)
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})
    # Même ordre de verrouillage que la planification : l'état du programme d'abord.
    planning.program_state(edition, lock=True)
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    _writable(edition, actor)
    before = snapshot(edition)
    changed = [name for name, value in data.items() if getattr(edition, name) != value]
    if not changed:
        return edition
    for name in changed:
        setattr(edition, name, data[name])
    try:
        edition.full_clean()
    except ValidationError as exc:
        raise Invalid(fields=exc.message_dict) from exc
    edition.save(update_fields=[*changed, "updated_at"])
    if "session_buffer_minutes" in changed:
        for session in Session.objects.filter(edition=edition).select_related("edition"):
            planning.reflow(session)
        planning.mark_changed(edition)
    after = snapshot(edition)
    record(
        "program.settings_changed",
        actor=actor,
        edition=edition,
        obj=edition,
        before={name: before[name] for name in changed},
        after={name: after[name] for name in changed},
    )
    return edition
