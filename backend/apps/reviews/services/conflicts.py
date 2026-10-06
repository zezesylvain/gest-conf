"""Conflits d'intérêts (RG-03 ; plan L4, H8).

- ``author`` : le relecteur est auteur de la soumission (compte, ou l'une de ses adresses) ;
  **bloquant sans exception** (plan L1 §5.5 : un ``SC_MEMBER`` également ``AUTHOR``).
- ``institution`` : même institution que l'un des auteurs (comparaison normalisée du profil du
  relecteur et des affiliations déclarées) ; bloquant, **levable** par le président avec un
  motif journalisé.
- ``declared`` : déclaré par le relecteur ou par le président ; bloquant, levable de même.

Les conflits détectés (``author``, ``institution``) sont recalculés à chaque contrôle : seule
leur levée est enregistrée (``ConflictOfInterest`` avec ``overridden_*``). Un conflit déclaré
est enregistré à la déclaration.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from allauth.account.models import EmailAddress
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Profile, User
from apps.accounts.services.roles import ensure_editable
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.reviews.models import (
    AssignmentStatus,
    ConflictKind,
    ConflictOfInterest,
    ConflictSource,
    ReviewAssignment,
)
from apps.submissions.models import Submission

# Conflits que le président peut lever, avec motif (H8).
OVERRIDABLE: frozenset[str] = frozenset({ConflictKind.INSTITUTION, ConflictKind.DECLARED})


def normalized_institution(name: str) -> str:
    """Institution comparée (H8) : sans accents, en minuscules, ponctuation retirée, espaces
    réduits. « Université Félix-Houphouët-Boigny » = « universite felix houphouet boigny ».
    Les abréviations (« Univ. ») ne sont pas résolues : le président déclare alors le conflit."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text).split())


@dataclass(frozen=True, slots=True)
class Conflict:
    kind: str
    overridden: bool

    @property
    def overridable(self) -> bool:
        return self.kind in OVERRIDABLE

    @property
    def blocking(self) -> bool:
        return not self.overridden


class ConflictDetector:
    """Conflits d'une soumission avec des relecteurs, calculés en un nombre fixe de requêtes
    (liste des candidats : pas de N+1)."""

    def __init__(self, submission: Submission, reviewers: Iterable[User]) -> None:
        self.submission = submission
        reviewers = list(reviewers)
        ids = [reviewer.pk for reviewer in reviewers]
        authors = list(submission.authors.all())
        self._author_users = {author.user_id for author in authors if author.user_id}
        self._author_users.add(submission.submitter_id)
        self._author_emails = {author.email.casefold() for author in authors if author.email}
        self._author_institutions = {
            key for key in (normalized_institution(a.institution) for a in authors) if key
        }
        self._emails: dict[int, set[str]] = {
            reviewer.pk: {reviewer.email.casefold()} for reviewer in reviewers
        }
        for user_id, email in EmailAddress.objects.filter(user_id__in=ids).values_list(
            "user_id", "email"
        ):
            self._emails[user_id].add(email.casefold())
        self._institutions = dict(
            Profile.objects.filter(user_id__in=ids).values_list("user_id", "institution")
        )
        self._rows: dict[tuple[int, str], ConflictOfInterest] = {
            (row.reviewer_id, row.kind): row
            for row in ConflictOfInterest.objects.filter(submission=submission, reviewer_id__in=ids)
        }

    def conflicts(self, reviewer: User) -> list[Conflict]:
        found: list[Conflict] = []
        if reviewer.pk in self._author_users or self._emails.get(reviewer.pk, set()) & (
            self._author_emails
        ):
            found.append(Conflict(ConflictKind.AUTHOR, overridden=False))
        institution = normalized_institution(self._institutions.get(reviewer.pk, ""))
        if institution and institution in self._author_institutions:
            found.append(self._conflict(reviewer, ConflictKind.INSTITUTION))
        if (reviewer.pk, ConflictKind.DECLARED) in self._rows:
            found.append(self._conflict(reviewer, ConflictKind.DECLARED))
        return found

    def _conflict(self, reviewer: User, kind: str) -> Conflict:
        row = self._rows.get((reviewer.pk, kind))
        return Conflict(kind, overridden=row is not None and row.overridden_at is not None)


def blocking_conflicts(submission: Submission, reviewer: User) -> list[Conflict]:
    """Conflits non levés de ``reviewer`` pour ``submission`` (RG-03)."""
    return [c for c in ConflictDetector(submission, [reviewer]).conflicts(reviewer) if c.blocking]


def override_conflicts(
    submission: Submission,
    reviewer: User,
    conflicts: Iterable[Conflict],
    *,
    reason: str,
    actor: Actor,
) -> None:
    """Lève des conflits levables (H8), dans la transaction de l'affectation. Journalisé
    (RG-17) ; l'appelant a vérifié la réauthentification récente (plan L4 §6)."""
    now = timezone.now()
    by = actor.user if actor.kind == ActorKind.USER else None
    for conflict in conflicts:
        row, _created = ConflictOfInterest.objects.get_or_create(
            submission=submission,
            reviewer=reviewer,
            kind=conflict.kind,
            defaults={"source": ConflictSource.SYSTEM},
        )
        row.overridden_by = by
        row.overridden_at = now
        row.overridden_reason = reason
        row.save(
            update_fields=["overridden_by", "overridden_at", "overridden_reason", "updated_at"]
        )
        record(
            "review.conflict_overridden",
            actor=actor,
            edition=submission.edition,
            obj=row,
            after={"submission": submission.reference, "reviewer": reviewer.pk, "kind": row.kind},
            reason=reason,
        )


@transaction.atomic
def declare_conflict(
    submission: Submission,
    reviewer: User,
    *,
    reason: str,
    actor: Actor,
    source: str = ConflictSource.CHAIR,
) -> ConflictOfInterest:
    """Conflit déclaré (H8), par le président ou par le relecteur. Une levée antérieure est
    effacée ; l'affectation active éventuelle est annulée, même si l'évaluation est envoyée
    (elle ne compte plus : RG-03). Journalisé."""
    from apps.reviews.services.assignments import end_assignment, lock_submission, reviewers_of

    submission = lock_submission(submission)
    if actor.kind != ActorKind.COMMAND:
        ensure_editable(submission.edition)
    if not reviewers_of(submission.edition).filter(pk=reviewer.pk).exists():
        message = _("Ce compte n'est pas membre du comité scientifique.")
        raise Invalid(fields={"reviewer": [message]})
    reason = reason.strip()
    if not reason:
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    row, _created = ConflictOfInterest.objects.update_or_create(
        submission=submission,
        reviewer=reviewer,
        kind=ConflictKind.DECLARED,
        defaults={
            "source": source,
            "reason": reason,
            "declared_by": actor.user if actor.kind == ActorKind.USER else None,
            "overridden_by": None,
            "overridden_at": None,
            "overridden_reason": "",
        },
    )
    record(
        "review.conflict_declared",
        actor=actor,
        edition=submission.edition,
        obj=row,
        after={"submission": submission.reference, "reviewer": reviewer.pk, "source": source},
        reason=reason,
    )
    active = ReviewAssignment.objects.filter(
        submission=submission, reviewer=reviewer, status=AssignmentStatus.ACTIVE
    ).first()
    if active is not None:
        end_assignment(active, AssignmentStatus.CANCELLED, reason=reason, actor=actor)
    return row
