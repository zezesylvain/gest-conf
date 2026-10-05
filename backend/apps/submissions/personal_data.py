"""Données personnelles des soumissions (registre ``apps.core.personal_data``, RG-18 ;
plan L3 F16).

- **Export** : ses soumissions (métadonnées, auteurs, fichiers sans contenu), et les
  soumissions d'autrui où il figure comme auteur.
- **Anonymisation** : refusée tant qu'une soumission active le concerne dans une édition
  non archivée (``submission_duties``, branché sur ``active_duties``). Sinon : brouillons
  supprimés ; ailleurs, sa ligne d'auteur est anonymisée et son nom et ses adresses sont
  retirés des clichés de révision et des motifs. La conservation des soumissions au-delà
  (actes, archives) relève de L8 et de Q14.
"""

from __future__ import annotations

import re
from typing import Any

from django.db.models import Q

from apps.conferences.models import EditionStatus
from apps.core.personal_data import (
    AnonymizationContext,
    register_duty_check,
    register_personal_data,
)
from apps.submissions.models import (
    StatusHistory,
    Submission,
    SubmissionAuthor,
    SubmissionRevision,
)
from apps.submissions.models import SubmissionStatus as S

ANONYMOUS = "Anonyme"
# Statuts qui n'engagent plus la personne (rien à transmettre avant l'anonymisation).
CLOSED_STATUSES = (S.DRAFT, S.WITHDRAWN)


def _involving(user) -> Q:
    return Q(submitter=user) | Q(authors__user=user)


def submission_duties(user) -> list[str]:
    """Soumissions actives qui empêchent l'anonymisation (F16)."""
    references = (
        Submission.objects.filter(_involving(user))
        .exclude(status__in=CLOSED_STATUSES)
        .exclude(edition__status=EditionStatus.ARCHIVED)
        .values_list("reference", flat=True)
        .distinct()
    )
    return sorted(f"submission:{reference}" for reference in references)


def _export(user) -> dict[str, Any]:
    own = (
        Submission.objects.filter(submitter=user)
        .select_related("edition")
        .prefetch_related("authors", "files")
        .order_by("id")
    )
    authored = (
        SubmissionAuthor.objects.filter(user=user)
        .exclude(submission__submitter=user)
        .select_related("submission")
        .order_by("id")
    )
    return {
        "submissions": [
            {
                "edition": item.edition.code,
                "reference": item.reference,
                "status": item.status,
                "title": item.title,
                "abstract": item.abstract,
                "keywords": item.keywords,
                "language": item.language,
                "submitted_at": item.submitted_at.isoformat() if item.submitted_at else None,
                "authors": [
                    {
                        "position": author.position,
                        "first_name": author.first_name,
                        "last_name": author.last_name,
                        "email": author.email,
                        "institution": author.institution,
                        "country": author.country,
                    }
                    for author in item.authors.all()
                ],
                "files": [
                    {
                        "kind": file.kind,
                        "version": file.version,
                        "original_name": file.original_name,
                        "size": file.size,
                        "sha256": file.sha256,
                    }
                    for file in item.files.all()
                ],
            }
            for item in own
        ],
        "authorships": [
            {
                "reference": author.submission.reference,
                "title": author.submission.title,
                "position": author.position,
            }
            for author in authored
        ],
    }


def _scrubber(context: AnonymizationContext):
    """Remplace nom et adresses (sans tenir compte de la casse), le plus long d'abord :
    « Prénom Nom » avant « Nom »."""
    needles = sorted({*context.original_emails, *context.names}, key=len, reverse=True)
    patterns = [re.compile(re.escape(needle), re.IGNORECASE) for needle in needles if needle]

    def scrub(value: Any) -> Any:
        if isinstance(value, str):
            for pattern in patterns:
                value = pattern.sub(ANONYMOUS, value)
            return value
        if isinstance(value, dict):
            return {key: scrub(item) for key, item in value.items()}
        if isinstance(value, list):
            return [scrub(item) for item in value]
        return value

    return scrub


def _anonymize(user, context: AnonymizationContext) -> None:
    from apps.submissions import storage

    # Brouillons : supprimés avec leurs fichiers (aucun numéro attribué, aucun tiers).
    for draft in Submission.objects.filter(submitter=user, status=S.DRAFT):
        storage.delete_all(draft)
        draft.authors.all().delete()
        draft.delete()

    emails = {email.lower() for email in context.original_emails}
    mine = Q(user=user) | Q(email__in=emails)
    submission_ids = sorted(
        set(SubmissionAuthor.objects.filter(mine).values_list("submission_id", flat=True))
        | set(Submission.objects.filter(submitter=user).values_list("id", flat=True))
    )
    for row in SubmissionAuthor.objects.filter(mine):
        row.first_name = ANONYMOUS
        row.last_name = ANONYMOUS
        row.email = f"author-{row.pk}@anonymized.invalid"
        row.institution = ""
        row.user = None
        row.save(update_fields=["first_name", "last_name", "email", "institution", "user"])
    scrub = _scrubber(context)
    for submission in Submission.objects.filter(pk__in=submission_ids).exclude(withdraw_reason=""):
        cleaned = scrub(submission.withdraw_reason)
        if cleaned != submission.withdraw_reason:
            submission.withdraw_reason = cleaned
            submission.save(update_fields=["withdraw_reason", "updated_at"])
    SubmissionRevision.redact(submission_ids, scrub)
    StatusHistory.redact(submission_ids, scrub)


def register_submissions_personal_data() -> None:
    from apps.core.personal_data import exempt_model

    register_personal_data(
        "submissions.submissions",
        models=(
            "submissions.Submission",
            "submissions.SubmissionAuthor",
            "submissions.SubmissionRevision",
            "submissions.StatusHistory",
        ),
        export=_export,
        anonymize=_anonymize,
        rank=500,
    )
    register_duty_check(submission_duties)
    exempt_model(
        "submissions.SubmissionFile",
        "uploaded_by : compte déposant, déjà couvert par la soumission ; contenu exporté par "
        "ses métadonnées, fichiers des brouillons supprimés à l'anonymisation.",
    )
    exempt_model(
        "submissions.SubmissionExtension",
        "granted_by : membre de la gestion qui accorde la dérogation (trace d'audit, sans "
        "texte libre le concernant).",
    )
