"""Confirmation de présentation et retraits (plan L5, I5).

Le soumissionnaire d'une communication dont la version finale est reçue désigne ses
présentateurs parmi les auteurs et confirme sa venue : ``CAMERA_READY_RECEIVED →
CONFIRMED`` par ``transition()`` (règle n° 4). Il peut ensuite changer de présentateurs ;
le programme est alors marqué modifié (révision), car les conflits de personnes en
dépendent (RG-12). Un retrait libère le créneau éventuel et prévient l'équipe du programme.
"""

from __future__ import annotations

from collections.abc import Sequence

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.actor import Actor, ActorKind
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation
from apps.program.models import PresentationConfirmation, Slot
from apps.program.services import planning
from apps.submissions import workflow
from apps.submissions.models import Submission
from apps.submissions.models import SubmissionStatus as S

# Statuts où l'auteur confirme (première fois) ou change ses présentateurs.
CONFIRMABLE = (S.CAMERA_READY_RECEIVED, S.CONFIRMED, S.SCHEDULED)
# Statuts d'une communication au programme (brouillon ou publié).
IN_PROGRAMME = (S.CONFIRMED, S.SCHEDULED)


def _positions(submission: Submission, presenters: Sequence[int]) -> list[int]:
    known = set(submission.authors.values_list("position", flat=True))
    if (
        not isinstance(presenters, (list, tuple))
        or not presenters
        or any(not isinstance(item, int) or isinstance(item, bool) for item in presenters)
    ):
        raise Invalid(fields={"presenters": [_("Désignez au moins un présentateur.")]})
    if len(set(presenters)) != len(presenters) or not set(presenters) <= known:
        raise Invalid(fields={"presenters": [_("Présentateurs à choisir parmi les auteurs.")]})
    return sorted(presenters)


@transaction.atomic
def confirm_presentation(
    submission: Submission, presenters: Sequence[int], *, actor: Actor
) -> Submission:
    """Désigne les présentateurs (positions des auteurs) ; confirme la communication à la
    première fois (I5). Réservé au soumissionnaire."""
    submission = Submission.objects.select_for_update().get(pk=submission.pk)
    if (
        actor.kind != ActorKind.USER
        or actor.user is None
        or actor.user.pk != submission.submitter_id
    ):
        raise NotAllowed()
    if submission.status not in CONFIRMABLE:
        raise RuleViolation(
            _("La présentation se confirme une fois la version finale reçue."),
            code=ErrorCode.INVALID_TRANSITION,
        )
    positions = _positions(submission, presenters)
    confirmation = PresentationConfirmation.objects.filter(submission=submission).first()
    if confirmation is None:
        confirmation = PresentationConfirmation.objects.create(
            submission=submission,
            presenters=positions,
            confirmed_at=timezone.now(),
            confirmed_by=actor.user,
        )
        record(
            "program.presentation_confirmed",
            actor=actor,
            edition=submission.edition,
            obj=submission,
            after=snapshot(confirmation),
        )
    elif confirmation.presenters != positions:
        before = snapshot(confirmation)
        confirmation.presenters = positions
        confirmation.save(update_fields=["presenters", "updated_at"])
        record(
            "program.presenters_changed",
            actor=actor,
            edition=submission.edition,
            obj=submission,
            before=before,
            after=snapshot(confirmation),
        )
        if submission.status in IN_PROGRAMME:
            # RG-12 : les conflits de personnes changent ; les planificateurs rechargent.
            planning.mark_changed(submission.edition)
    if submission.status == S.CAMERA_READY_RECEIVED:
        submission = workflow.transition(submission, S.CONFIRMED, actor)
    return submission


def guard_confirmation(submission: Submission, to_status: str, now) -> None:
    """I5 : pas de confirmation sans présentateurs enregistrés (RG-11 s'y ajoutera en L6)."""
    if (
        to_status == S.CONFIRMED
        and submission.status == S.CAMERA_READY_RECEIVED
        and not PresentationConfirmation.objects.filter(submission=submission).exists()
    ):
        raise RuleViolation(
            _("Désignez d'abord les présentateurs."), code=ErrorCode.INVALID_TRANSITION
        )


def on_transition(submission: Submission, from_status: str, to_status: str, actor: Actor) -> None:
    """Retrait d'une communication confirmée ou programmée : créneau libéré (journalisé),
    équipe du programme prévenue (I5)."""
    from apps.program.notifications import withdrawn_from_programme

    if to_status != S.WITHDRAWN or from_status not in IN_PROGRAMME:
        return
    slot = Slot.objects.filter(submission=submission).select_related("session__edition").first()
    if slot is not None:
        planning.remove_slot(slot, actor=actor)
    withdrawn_from_programme(submission, was_placed=slot is not None)
