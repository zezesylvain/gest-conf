"""Données personnelles des questionnaires (plan L8, N15) : les invitations seulement ; les
réponses, anonymes, ne sont pas des données personnelles (RG-21)."""

from __future__ import annotations

from typing import Any

from apps.core.personal_data import AnonymizationContext
from apps.surveys.models import SurveyInvitation


def export_surveys(user: Any) -> dict[str, Any]:
    rows = SurveyInvitation.objects.filter(user=user).select_related("survey__edition")
    return {
        "survey_invitations": [
            {
                "edition": row.survey.edition.code,
                "survey": row.survey.title_fr,
                "invited_on": row.invited_on.isoformat(),
                "reminded_on": row.reminded_on.isoformat() if row.reminded_on else None,
                "answered_on": row.answered_on.isoformat() if row.answered_on else None,
            }
            for row in rows.order_by("invited_on", "id")
        ]
    }


def anonymize_surveys(user: Any, context: AnonymizationContext) -> None:
    """Les invitations restent rattachées au compte anonymisé (taux de réponse) ; elles ne
    disent rien de la réponse, qui n'est liée à personne."""
