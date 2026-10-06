"""Classement, décisions, publication et version finale (plan L4, H16, H18 ; RG-09, RG-10 ;
US-06).

- **Décision provisoire** (H16) : issue et format attribué, individuelle ou en lot, sur une
  soumission évaluée (RG-07) ; modifiable ou annulable tant qu'elle n'est pas publiée. Une
  décision enregistrée fige les évaluations (RG-06 : « modifiable jusqu'à la décision »).
- **Publication** (RG-09) : les statuts changent (``transition()``, capacité
  ``decisions.publish`` revérifiée) et les auteurs sont prévenus à ce moment seulement ; pas
  d'annulation de publication. Liste d'attente → acceptée ensuite, par le président.
- **Version finale** (H18) : PDF nominatif (non nettoyé) et lettre de réponse (obligatoire
  pour ``accepted_minor``) jusqu'à la date clé ``camera_ready``.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.accounts.services.invitations import display_name
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, KeyDateCode, SubmissionType
from apps.conferences.services import key_date
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import DomainError, ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.reviews.models import (
    AssignmentStatus,
    Decision,
    DecisionOutcome,
    FinalVersion,
    Review,
    ReviewStatus,
)
from apps.reviews.services.assignments import lock_submission
from apps.reviews.services.reviews import summary
from apps.submissions import workflow
from apps.submissions.models import Submission, SubmissionFile, SubmissionFileKind
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.services import csv_cell

# Issue → statut atteint à la publication (H16 ; REVISION_REQUESTED n'est pas utilisé).
OUTCOME_STATUS: Mapping[str, str] = {
    DecisionOutcome.ACCEPTED: S.ACCEPTED,
    DecisionOutcome.ACCEPTED_MINOR: S.ACCEPTED_MINOR,
    DecisionOutcome.WAITLIST: S.WAITLIST,
    DecisionOutcome.REJECTED: S.REJECTED,
}
ACCEPTED_OUTCOMES = (DecisionOutcome.ACCEPTED, DecisionOutcome.ACCEPTED_MINOR)
FINAL_STATUSES = (S.ACCEPTED, S.ACCEPTED_MINOR, S.CAMERA_READY_RECEIVED)
COMMENT_MAX = 20_000
LETTER_MAX = 50_000


def _actor_user(actor: Actor):
    return actor.user if actor.kind == ActorKind.USER else None


# --- Décisions provisoires (H16) ------------------------------------------------------------


def _assigned_type(submission: Submission, outcome: str, code: str | None) -> SubmissionType | None:
    if code:
        found = SubmissionType.objects.filter(edition=submission.edition_id, code=code).first()
        if found is None:
            raise Invalid(fields={"assigned_type": [_("Type de communication inconnu.")]})
        return found
    return submission.submission_type if outcome in ACCEPTED_OUTCOMES else None


@transaction.atomic
def record_decision(
    submission: Submission,
    *,
    outcome: str,
    actor: Actor,
    assigned_type: str | None = None,
    comment_to_authors: str = "",
    now: datetime | None = None,
) -> Decision:
    """Décision provisoire (H16), journalisée ; droit ``decisions.decide`` vérifié par la vue
    (règle n° 2)."""
    now = now or timezone.now()
    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    if outcome not in OUTCOME_STATUS:
        raise Invalid(fields={"outcome": [_("Issue inconnue.")]})
    current = Decision.objects.filter(submission=submission).first()
    if current is not None and current.published_at is not None:
        raise RuleViolation(_("Décision déjà publiée."), code=ErrorCode.INVALID_TRANSITION)
    if submission.status != S.REVIEWED:
        raise RuleViolation(
            _("Décision possible une fois la soumission évaluée (RG-07)."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    comment = (comment_to_authors or "").strip()
    if len(comment) > COMMENT_MAX:
        raise Invalid(fields={"comment_to_authors": [_("Texte trop long.")]})
    kind = _assigned_type(submission, outcome, assigned_type)
    before = (
        {"outcome": current.outcome, "assigned_type": getattr(current.assigned_type, "code", None)}
        if current is not None
        else None
    )
    decision, _created = Decision.objects.update_or_create(
        submission=submission,
        defaults={
            "outcome": outcome,
            "assigned_type": kind,
            "comment_to_authors": comment,
            "decided_by": _actor_user(actor),
            "decided_at": now,
        },
    )
    record(
        "decision.recorded",
        actor=actor,
        edition=submission.edition,
        obj=decision,
        before=before,
        after={
            "submission": submission.reference,
            "outcome": outcome,
            "assigned_type": kind.code if kind else None,
        },
    )
    return decision


@transaction.atomic
def record_decisions(
    edition: Edition, items: Iterable[Mapping[str, Any]], *, actor: Actor
) -> list[Decision]:
    """Décisions en lot (H16) : tout ou rien ; les refus sont rendus par ligne."""
    ensure_editable(edition)
    decisions: list[Decision] = []
    errors: dict[str, list[str]] = {}
    for index, item in enumerate(items):
        try:
            with transaction.atomic():
                decisions.append(
                    record_decision(
                        item["submission"],
                        outcome=item["outcome"],
                        assigned_type=item.get("assigned_type"),
                        comment_to_authors=item.get("comment_to_authors", ""),
                        actor=actor,
                    )
                )
        except DomainError as error:
            reference = item["submission"].reference or item["submission"].pk
            messages = [str(error.message)] + [
                str(m) for field in error.fields.values() for m in field
            ]
            errors[str(index)] = [f"{reference} : {' '.join(messages)}"]
    if errors:
        raise Invalid(_("Décisions refusées : rien n'a été enregistré."), fields=errors)
    return decisions


@transaction.atomic
def cancel_decision(submission: Submission, *, actor: Actor) -> None:
    """Annule une décision **provisoire** ; les évaluations redeviennent modifiables."""
    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    decision = Decision.objects.filter(submission=submission).first()
    if decision is None:
        return
    if decision.published_at is not None:
        raise RuleViolation(_("Décision déjà publiée."), code=ErrorCode.INVALID_TRANSITION)
    record(
        "decision.cancelled",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        before={"outcome": decision.outcome},
    )
    decision.delete()


# --- Publication (RG-09) --------------------------------------------------------------------


@transaction.atomic
def publish_decisions(edition: Edition, *, actor: Actor, now: datetime | None = None) -> int:
    """Publie les décisions provisoires de l'édition (RG-09) : statuts par ``transition()``,
    e-mails et notifications aux auteurs ; journalisé. Renvoie le nombre de décisions."""
    from apps.reviews.notifications import decision_published

    now = now or timezone.now()
    ensure_editable(edition)
    pending = list(
        Decision.objects.select_for_update()
        .filter(
            submission__edition=edition,
            published_at__isnull=True,
            submission__status=S.REVIEWED,
        )
        .select_related("submission", "assigned_type")
        .order_by("submission__reference", "submission_id")
    )
    for decision in pending:
        workflow.transition(decision.submission, OUTCOME_STATUS[decision.outcome], actor, now=now)
        decision.published_at = now
        decision.save(update_fields=["published_at", "updated_at"])
        decision_published(decision)
    record(
        "decision.published",
        actor=actor,
        edition=edition,
        obj=edition,
        after={
            "count": len(pending),
            "outcomes": dict(Counter(decision.outcome for decision in pending)),
        },
    )
    return len(pending)


@transaction.atomic
def promote(submission: Submission, *, actor: Actor) -> Decision:
    """Liste d'attente → acceptée, après publication (H16) ; auteurs prévenus."""
    from apps.reviews.notifications import decision_published

    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    decision = Decision.objects.filter(submission=submission).first()
    if submission.status != S.WAITLIST or decision is None or decision.published_at is None:
        raise RuleViolation(
            _("Seule une soumission en liste d'attente publiée peut être acceptée."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    decision.outcome = DecisionOutcome.ACCEPTED
    if decision.assigned_type_id is None:
        decision.assigned_type = submission.submission_type
    decision.save(update_fields=["outcome", "assigned_type", "updated_at"])
    workflow.transition(submission, S.ACCEPTED, actor)
    record(
        "decision.promoted",
        actor=actor,
        edition=submission.edition,
        obj=decision,
        before={"outcome": DecisionOutcome.WAITLIST},
        after={"submission": submission.reference, "outcome": DecisionOutcome.ACCEPTED},
    )
    decision_published(decision)
    return decision


def guard_decisions(submission: Submission, to_state: str, now: datetime) -> None:
    """Garde du workflow : un statut de décision n'est atteint qu'avec la décision
    correspondante (RG-09) ; la version finale n'est reçue qu'avec son dépôt (H18)."""
    if to_state in OUTCOME_STATUS.values() and submission.status in (S.REVIEWED, S.WAITLIST):
        decision = Decision.objects.filter(submission=submission).first()
        if decision is None or OUTCOME_STATUS[decision.outcome] != to_state:
            raise RuleViolation(
                _("Aucune décision correspondante."), code=ErrorCode.INVALID_TRANSITION
            )
    elif (
        to_state == S.CAMERA_READY_RECEIVED
        and not FinalVersion.objects.filter(submission=submission).exists()
    ):
        raise RuleViolation(_("Version finale absente."), code=ErrorCode.INVALID_TRANSITION)


# --- Vue de l'auteur (RG-09, RG-10) ---------------------------------------------------------


def published_decision(submission: Submission) -> Decision | None:
    """RG-09 : la décision n'existe pour l'auteur qu'une fois publiée."""
    decision = (
        Decision.objects.filter(submission=submission, published_at__isnull=False)
        .select_related("assigned_type")
        .first()
    )
    return decision


def comments_for_authors(submission: Submission) -> list[dict[str, Any]]:
    """RG-10 : commentaires aux auteurs des évaluations retenues, sous pseudonyme ; jamais
    l'identité des relecteurs, leurs notes ni les commentaires au comité."""
    reviews = (
        Review.objects.filter(
            assignment__submission=submission,
            assignment__status=AssignmentStatus.ACTIVE,
            status=ReviewStatus.SUBMITTED,
        )
        .exclude(comment_to_authors="")
        .order_by("assignment__pseudonym_rank", "id")
        .values_list("assignment__pseudonym_rank", "comment_to_authors")
    )
    return [{"pseudonym_rank": rank, "comment": comment} for rank, comment in reviews]


# --- Classement et simulation (US-06) -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RankedSubmission:
    submission: Submission
    final: Decimal | None
    spread: Decimal
    divergent: bool
    review_count: int
    recommendations: dict[str, int]
    decision: Decision | None


def ranking(
    edition: Edition,
    *,
    track: str | None = None,
    submission_type: str | None = None,
) -> list[RankedSubmission]:
    """Soumissions évaluées ou décidées, par note finale décroissante (sans note : à la fin)."""
    submissions = (
        Submission.objects.filter(edition=edition)
        .filter(status__in=(S.UNDER_REVIEW, S.REVIEWED, *OUTCOME_STATUS.values(), *FINAL_STATUSES))
        .exclude(status=S.REJECTED, decision__isnull=True)  # rejet de recevabilité
        .select_related("edition", "track", "submission_type", "decision__assigned_type")
    )
    if track:
        submissions = submissions.filter(track__code=track)
    if submission_type:
        submissions = submissions.filter(submission_type__code=submission_type)
    rows = []
    for submission in submissions:
        state = summary(submission)
        rows.append(
            RankedSubmission(
                submission=submission,
                final=state.final,
                spread=state.spread,
                divergent=state.divergent,
                review_count=len(state.reviews),
                recommendations=dict(Counter(r.recommendation for r in state.reviews)),
                decision=getattr(submission, "decision", None),
            )
        )
    rows.sort(
        key=lambda row: (
            row.final is None,
            -(row.final or Decimal(0)),
            row.submission.reference or "",
        )
    )
    return rows


def simulate(rows: list[RankedSubmission], threshold: Decimal) -> dict[str, Any]:
    """US-06 : ce que donnerait un seuil d'acceptation, au total, par type et par thématique."""

    def tally(key) -> list[dict[str, Any]]:
        groups: dict[str | None, dict[str, Any]] = {}
        for row in rows:
            code = key(row.submission)
            entry = groups.setdefault(code, {"code": code, "total": 0, "accepted": 0})
            entry["total"] += 1
            if row.final is not None and row.final >= threshold:
                entry["accepted"] += 1
        return sorted(groups.values(), key=lambda item: item["code"] or "")

    return {
        "threshold": threshold,
        "accepted": sum(1 for row in rows if row.final is not None and row.final >= threshold),
        "total": len(rows),
        "by_type": tally(lambda s: s.submission_type.code if s.submission_type else None),
        "by_track": tally(lambda s: s.track.code if s.track else None),
    }


# --- Version finale (H18) -------------------------------------------------------------------


@transaction.atomic
def submit_final_version(
    submission: Submission,
    *,
    data: bytes,
    name: str,
    response_letter: str,
    actor: Actor,
    now: datetime | None = None,
) -> FinalVersion:
    """Dépôt (ou remplacement) de la version finale par le soumissionnaire (H18)."""
    from apps.submissions import pdf, storage
    from apps.submissions.notifications import final_version_received
    from apps.submissions.services import _safe_name

    now = now or timezone.now()
    submission = lock_submission(submission)
    ensure_editable(submission.edition)
    user = _actor_user(actor)
    if user is None or user.pk != submission.submitter_id:
        raise NotAllowed()
    decision = published_decision(submission)
    if submission.status not in FINAL_STATUSES or decision is None:
        raise RuleViolation(
            _("Version finale attendue pour une soumission acceptée."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    deadline = key_date(submission.edition, KeyDateCode.CAMERA_READY)
    if deadline is not None and now >= deadline:
        raise RuleViolation(
            _("La date limite de la version finale est passée."),
            code=ErrorCode.DEADLINE_PASSED,
        )
    letter = (response_letter or "").strip()
    if len(letter) > LETTER_MAX:
        raise Invalid(fields={"response_letter": [_("Texte trop long.")]})
    if decision.outcome == DecisionOutcome.ACCEPTED_MINOR and not letter:
        raise Invalid(
            fields={"response_letter": [_("Lettre de réponse aux relecteurs obligatoire.")]}
        )
    if not name.lower().endswith(".pdf"):
        raise Invalid(fields={"file": [_("Fichier PDF attendu (.pdf).")]})
    kind = submission.submission_type
    limit = (kind.max_file_mb if kind else 10) * 1024 * 1024
    if len(data) > limit:
        raise Invalid(fields={"file": [_("Fichier trop volumineux.")]})
    checked = pdf.check_pdf(data, anonymize=False)  # version nominative (H18)
    storage_name, digest = storage.write(checked.data)
    previous = SubmissionFile.objects.filter(
        submission=submission, kind=SubmissionFileKind.CAMERA_READY
    ).aggregate(Max("version"))["version__max"]
    SubmissionFile.objects.filter(
        submission=submission, kind=SubmissionFileKind.CAMERA_READY, is_current=True
    ).update(is_current=False, updated_at=now)
    stored = SubmissionFile.objects.create(
        submission=submission,
        kind=SubmissionFileKind.CAMERA_READY,
        version=(previous or 0) + 1,
        storage_name=storage_name,
        original_name=_safe_name(name),
        size=len(checked.data),
        sha256=digest,
        pages=checked.pages,
        metadata_removed=False,
        uploaded_by=user,
    )
    final, _created = FinalVersion.objects.update_or_create(
        submission=submission,
        defaults={"file": stored, "response_letter": letter, "submitted_at": now},
    )
    record(
        "submission.final_version_uploaded",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        after={"version": stored.version, "pages": stored.pages},
    )
    if submission.status != S.CAMERA_READY_RECEIVED:
        workflow.transition(submission, S.CAMERA_READY_RECEIVED, actor, now=now)
    final_version_received(submission, stored)
    return final


# --- Export des évaluations (RG-17) ---------------------------------------------------------


def export_reviews_csv(edition: Edition, *, actor: Actor) -> str:
    """Évaluations envoyées de l'édition, une ligne par évaluation, avec le nom du relecteur
    (``reviews.read_all``), la note finale et la décision. Même format que l'export des
    soumissions (« ; », BOM, cellules neutralisées) ; journalisé (export de masse)."""
    zone = ZoneInfo(edition.timezone)
    reviews = list(
        Review.objects.filter(
            assignment__submission__edition=edition,
            assignment__status=AssignmentStatus.ACTIVE,
            status=ReviewStatus.SUBMITTED,
        )
        .select_related(
            "assignment__reviewer__profile",
            "assignment__submission__track",
            "assignment__submission__submission_type",
            "assignment__submission__decision__assigned_type",
            "suggested_type",
        )
        .prefetch_related("scores__criterion")
        .order_by("assignment__submission__reference", "assignment__pseudonym_rank", "id")
    )
    codes = sorted({score.criterion.code for review in reviews for score in review.scores.all()})
    finals: dict[int, Decimal | None] = {}
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            str(_("Référence")),
            str(_("Titre")),
            str(_("Thématique")),
            str(_("Type")),
            str(_("Statut")),
            str(_("Note finale")),
            str(_("Décision")),
            str(_("Relecteur")),
            str(_("Pseudonyme")),
            str(_("Note pondérée")),
            str(_("Recommandation")),
            str(_("Confiance")),
            str(_("Éthique")),
            str(_("Plagiat")),
            str(_("Format suggéré")),
            str(_("Commentaire aux auteurs")),
            str(_("Commentaire au comité")),
            str(_("Envoyée le")),
            str(_("Version")),
            *codes,
        ]
    )
    for review in reviews:
        submission = review.assignment.submission
        if submission.pk not in finals:
            finals[submission.pk] = summary(submission).final
        decision = getattr(submission, "decision", None)
        scores = {score.criterion.code: score.value for score in review.scores.all()}
        submitted = review.submitted_at.astimezone(zone).strftime("%Y-%m-%d %H:%M")
        writer.writerow(
            [
                csv_cell(value)
                for value in (
                    submission.reference or "",
                    submission.title,
                    submission.track.code if submission.track else "",
                    submission.submission_type.code if submission.submission_type else "",
                    submission.status,
                    finals[submission.pk] if finals[submission.pk] is not None else "",
                    decision.outcome if decision else "",
                    display_name(review.assignment.reviewer),
                    review.assignment.pseudonym_rank,
                    review.weighted_score if review.weighted_score is not None else "",
                    review.recommendation,
                    review.confidence or "",
                    "1" if review.ethics_flag else "",
                    "1" if review.plagiarism_flag else "",
                    review.suggested_type.code if review.suggested_type else "",
                    review.comment_to_authors,
                    review.comment_to_committee,
                    submitted,
                    review.version,
                    *(scores.get(code, "") for code in codes),
                )
            ]
        )
    record(
        "review.exported",
        actor=actor,
        edition=edition,
        obj=edition,
        after={"count": len(reviews)},
    )
    return "﻿" + output.getvalue()
