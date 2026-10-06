"""Workflow des soumissions (règle n° 4 ; étude §5.1 ; plan L3 §2.2).

``transition(submission, to_state, actor)`` est le **seul** chemin qui écrit ``status`` :
il vérifie la légalité de la transition, les droits de l'acteur et les gardes métier,
écrit ``StatusHistory`` et le journal d'audit, puis déclenche les effets (notifications
mises en file dans la même transaction, envoyées après validation). Un méta-test vérifie
qu'aucun autre module n'écrit ``status``.

La table reprend **toutes** les transitions de l'étude ; celles des lots suivants sont
déclarées mais refusées (``invalid_transition``) jusqu'à leur lot.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.conferences.models import EditionStatus
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.counters import next_value
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.submissions.models import StatusHistory, Submission, reference_scope
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.services import active_extension, call_closed_at, can_write, missing_items


class Who(StrEnum):
    """Qui peut déclencher une transition (les droits fins des comités arrivent en L4)."""

    SUBMITTER = "submitter"
    SYSTEM = "system"  # commande ou tâche planifiée
    SC = "sc"  # président du CS (L4)
    ORGANIZERS = "organizers"  # CO, présence, inscription (L5 à L7)


@dataclass(frozen=True, slots=True)
class Rule:
    who: Who
    lot: str  # lot qui active la transition
    available: bool = False


# Étude §5.1, transition par transition. REVISION_REQUESTED (statut de M6) n'a aucune
# transition dans le diagramme de l'étude : écart signalé, à préciser en L4.
TRANSITIONS: dict[tuple[str, str], Rule] = {
    (S.DRAFT, S.SUBMITTED): Rule(Who.SUBMITTER, "L3", available=True),
    (S.SUBMITTED, S.SCREENING): Rule(Who.SYSTEM, "L3", available=True),
    (S.DRAFT, S.WITHDRAWN): Rule(Who.SUBMITTER, "L3", available=True),
    (S.SUBMITTED, S.WITHDRAWN): Rule(Who.SUBMITTER, "L3", available=True),
    (S.SCREENING, S.UNDER_REVIEW): Rule(Who.SC, "L4"),
    (S.SCREENING, S.REJECTED): Rule(Who.SC, "L4"),
    (S.UNDER_REVIEW, S.REVIEWED): Rule(Who.SYSTEM, "L4"),
    (S.REVIEWED, S.ACCEPTED): Rule(Who.SC, "L4"),
    (S.REVIEWED, S.ACCEPTED_MINOR): Rule(Who.SC, "L4"),
    (S.REVIEWED, S.WAITLIST): Rule(Who.SC, "L4"),
    (S.REVIEWED, S.REJECTED): Rule(Who.SC, "L4"),
    (S.WAITLIST, S.ACCEPTED): Rule(Who.SC, "L4"),
    (S.ACCEPTED, S.CAMERA_READY_RECEIVED): Rule(Who.SUBMITTER, "L4"),
    (S.ACCEPTED_MINOR, S.CAMERA_READY_RECEIVED): Rule(Who.SUBMITTER, "L4"),
    (S.ACCEPTED, S.WITHDRAWN): Rule(Who.SUBMITTER, "L4"),
    (S.CAMERA_READY_RECEIVED, S.CONFIRMED): Rule(Who.SYSTEM, "L6"),
    (S.CONFIRMED, S.SCHEDULED): Rule(Who.ORGANIZERS, "L5"),
    (S.SCHEDULED, S.PRESENTED): Rule(Who.ORGANIZERS, "L7"),
    (S.PRESENTED, S.PUBLISHED): Rule(Who.ORGANIZERS, "L10"),
}

# Effets de la transition, dans sa transaction (notifications, L3.2) : f(submission,
# from_status, to_status, actor).
type Effect = Callable[[Submission, str, str, Actor], None]
_EFFECTS: list[Effect] = []


def register_effect(effect: Effect) -> None:
    if effect not in _EFFECTS:
        _EFFECTS.append(effect)


def allowed_targets(submission: Submission) -> list[str]:
    """Statuts atteignables depuis le statut courant (transitions disponibles)."""
    return [
        to for (frm, to), rule in TRANSITIONS.items() if frm == submission.status and rule.available
    ]


def _check_actor(rule: Rule, submission: Submission, actor: Actor) -> None:
    if rule.who == Who.SUBMITTER:
        if actor.kind != ActorKind.USER or actor.user is None:
            raise NotAllowed()
        if actor.user.pk != submission.submitter_id:
            raise NotAllowed()
    elif rule.who == Who.SYSTEM:
        if actor.kind not in (ActorKind.SYSTEM, ActorKind.COMMAND):
            raise NotAllowed()
    else:  # pragma: no cover - aucune transition disponible de ces familles en L3
        raise NotAllowed()


def _guard(submission: Submission, to_state: str, reason: str, now: datetime) -> None:
    """Gardes métier des transitions de L3."""
    if to_state == S.SUBMITTED:
        if not can_write(submission, now):
            raise RuleViolation(_("L'appel à communications est clos."), code=ErrorCode.CALL_CLOSED)
        problems = missing_items(submission)
        if problems:
            raise RuleViolation(
                _("La soumission est incomplète."),
                code=ErrorCode.SUBMISSION_INCOMPLETE,
                fields=problems,
            )
    elif to_state == S.SCREENING:
        closes = call_closed_at(submission)
        if closes is None or now < closes or active_extension(submission, now) is not None:
            raise RuleViolation(
                _("La recevabilité commence à la clôture de l'appel (et des dérogations)."),
                code=ErrorCode.INVALID_TRANSITION,
            )
    elif to_state == S.WITHDRAWN and submission.status != S.DRAFT and not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})


@transaction.atomic
def transition(
    submission: Submission,
    to_state: str,
    actor: Actor,
    *,
    reason: str = "",
    now: datetime | None = None,
) -> Submission:
    """Fait passer ``submission`` à ``to_state`` (règle n° 4). Lève ``RuleViolation``
    (``invalid_transition``, ``call_closed``, ``submission_incomplete``), ``NotAllowed``
    ou ``Invalid`` ; rien n'est écrit en cas de refus."""
    now = now or timezone.now()
    submission = (
        Submission.objects.select_for_update()
        .select_related("edition", "track", "submission_type")
        .get(pk=submission.pk)
    )
    from_state = submission.status
    rule = TRANSITIONS.get((from_state, to_state))
    if rule is None or not rule.available:
        raise RuleViolation(
            _("Changement de statut non autorisé."), code=ErrorCode.INVALID_TRANSITION
        )
    if submission.edition.status == EditionStatus.ARCHIVED:
        raise RuleViolation(code=ErrorCode.EDITION_ARCHIVED)
    _check_actor(rule, submission, actor)
    _guard(submission, to_state, reason, now)

    fields = ["status", "revision", "updated_at"]
    submission.status = to_state
    submission.revision += 1
    if to_state == S.SUBMITTED:
        if submission.reference is None:
            # F4 : numéro attribué à la première soumission, dans cette transaction.
            number = next_value(reference_scope(submission.edition))
            submission.reference = f"{submission.edition.code}-{number:04d}"
            fields.append("reference")
        submission.submitted_at = now
        fields.append("submitted_at")
    elif to_state == S.WITHDRAWN:
        submission.withdrawn_at = now
        submission.withdraw_reason = reason.strip()
        fields += ["withdrawn_at", "withdraw_reason"]
    submission.save(update_fields=fields)

    StatusHistory.objects.create(
        submission=submission,
        from_status=from_state,
        to_status=to_state,
        actor=actor.user if actor.kind == ActorKind.USER else None,
        actor_label=actor.label,
        reason=reason.strip(),
        at=now,
    )
    record(
        "submission.status_changed",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        before={"status": from_state},
        after={"status": to_state, "reference": submission.reference},
        reason=reason.strip(),
    )
    # Effets dans la transaction : les e-mails sont mis en file (outbox) avec la transition,
    # ou pas du tout ; l'envoi a lieu après validation (file de tâches).
    for effect in list(_EFFECTS):
        effect(submission, from_state, to_state, actor)
    return submission
