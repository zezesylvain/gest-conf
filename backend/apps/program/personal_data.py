"""Données personnelles du programme (registre ``apps.core.personal_data``, RG-18 ; plan L5
§3). Concernent une personne : ses rôles de séance, ses créneaux d'intervenant invité, les
confirmations de présentation qu'elle a faites, et son nom dans les programmes publiés.

- **Export** : rôles de séance, créneaux d'intervenant invité, confirmations de présentation.
- **Anonymisation** : refusée tant que la personne tient un rôle de séance ou un créneau
  d'intervenant dans une édition non archivée (``program_duties``, comme F16). Sinon : rôles
  et créneaux conservés (le compte est anonymisé) ; son nom et ses adresses retirés des
  instantanés publiés (``ProgramPublication.redact``).
"""

from __future__ import annotations

from typing import Any

from apps.conferences.models import EditionStatus
from apps.core.personal_data import (
    AnonymizationContext,
    exempt_model,
    register_duty_check,
    register_personal_data,
)
from apps.program.models import PresentationConfirmation, ProgramPublication, SessionRole, Slot
from apps.submissions.personal_data import _scrubber


def program_duties(user) -> list[str]:
    roles = (
        SessionRole.objects.filter(user=user)
        .exclude(session__edition__status=EditionStatus.ARCHIVED)
        .values_list("session__edition__code", flat=True)
    )
    slots = (
        Slot.objects.filter(speaker=user)
        .exclude(session__edition__status=EditionStatus.ARCHIVED)
        .values_list("session__edition__code", flat=True)
    )
    return sorted({f"program:{code}" for code in [*roles, *slots]})


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    return {
        "session_roles": [
            {
                "edition": row.session.edition.code,
                "session": row.session.title_fr,
                "role": row.role,
                "starts_at": _iso(row.session.starts_at),
            }
            for row in SessionRole.objects.filter(user=user)
            .select_related("session__edition")
            .order_by("session__starts_at", "id")
        ],
        "speaker_slots": [
            {
                "edition": row.session.edition.code,
                "title": row.title_fr,
                "starts_at": _iso(row.starts_at),
                "duration_min": row.duration_min,
            }
            for row in Slot.objects.filter(speaker=user)
            .select_related("session__edition")
            .order_by("starts_at", "id")
        ],
        "presentation_confirmations": [
            {
                "reference": row.submission.reference,
                "presenters": row.presenters,
                "confirmed_at": _iso(row.confirmed_at),
            }
            for row in PresentationConfirmation.objects.filter(confirmed_by=user)
            .select_related("submission")
            .order_by("confirmed_at", "id")
        ],
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    edition_ids = list(ProgramPublication.objects.values_list("edition_id", flat=True).distinct())
    ProgramPublication.redact(edition_ids, _scrubber(context))


def register_program_personal_data() -> None:
    register_personal_data(
        "program.program",
        models=("program.SessionRole", "program.Slot", "program.PresentationConfirmation"),
        export=_export,
        anonymize=_anonymize,
        rank=460,
    )
    register_duty_check(program_duties)
    exempt_model(
        "program.ProgramPublication",
        "published_by : membre qui publie (trace de gestion) ; les noms des instantanés sont "
        "retirés par l'anonymisation de chaque personne concernée.",
    )
