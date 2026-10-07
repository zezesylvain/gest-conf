"""Contrôles d'intégrité des questionnaires (plan L8, N17)."""

from __future__ import annotations

from django.db.models import Count, Q

from apps.surveys.models import Survey


def check_responses() -> list[str]:
    """Autant de réponses que d'invitations marquées « répondu » ; aucune réponse à un
    questionnaire jamais publié."""
    problems = []
    rows = Survey.objects.annotate(
        responses_count=Count("responses", distinct=True),
        answered=Count(
            "invitations", filter=Q(invitations__answered_on__isnull=False), distinct=True
        ),
    )
    for survey in rows:
        if survey.responses_count != survey.answered:
            problems.append(
                f"questionnaire {survey.pk} : {survey.responses_count} réponses pour "
                f"{survey.answered} invitations marquées « répondu »"
            )
        if survey.status == "draft" and survey.responses_count:
            problems.append(f"questionnaire {survey.pk} : réponses à un brouillon")
    return problems
