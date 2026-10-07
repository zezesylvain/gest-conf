"""Régimes alimentaires (plan L8, N7 ; RG-23 proposée).

**RG-23** : un régime n'est recueilli qu'avec un **consentement explicite** (la donnée peut
révéler la santé ou des convictions), retirable à tout moment ; il ne sert qu'à la
restauration ; les noms ne sont visibles que de ``logistics.read``, et seulement par un export
journalisé sous réauthentification ; ailleurs, des effectifs agrégés ; il est **effacé 30 jours
après la fin de l'édition** ou à son archivage.

Peuvent déclarer : les personnes qui ont un rôle actif dans l'édition ou une inscription en
attente ou confirmée. Le contenu d'une déclaration n'entre jamais au journal.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, EditionStatus
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.logistics.models import Diet, DietaryDeclaration

RETENTION = timedelta(days=30)
ALLERGIES_MAX_LENGTH = 200


def retention_filter(now) -> Q:
    """Éditions archivées, ou finies depuis plus de 30 jours (même règle que les numéros de
    passeport de L7, K14)."""
    limit = (now - RETENTION).date()
    return Q(edition__status=EditionStatus.ARCHIVED) | Q(edition__end_date__lt=limit)


def eligible(edition: Edition, user: User) -> bool:
    from apps.registrations.models import ACTIVE_STATUSES, Registration

    return (
        UserRole.objects.filter(edition=edition, user=user, status=UserRoleStatus.ACTIVE).exists()
        or Registration.objects.filter(
            edition=edition, user=user, status__in=ACTIVE_STATUSES
        ).exists()
    )


def declaration_of(edition: Edition, user: User) -> DietaryDeclaration | None:
    return DietaryDeclaration.objects.filter(edition=edition, user=user).first()


@transaction.atomic
def declare(
    edition: Edition,
    user: User,
    *,
    diets: Iterable[str],
    allergies: str,
    consent: bool,
    actor: Actor,
) -> DietaryDeclaration:
    """RG-23 : déclaration ou mise à jour, consentement explicite exigé à chaque fois."""
    ensure_editable(edition)
    if not consent:
        raise Invalid(
            fields={"consent": [_("Votre accord est nécessaire pour enregistrer un régime.")]}
        )
    if not eligible(edition, user):
        raise Invalid(fields={"edition": [_("Inscription ou rôle dans l'édition nécessaire.")]})
    values = sorted(set(diets))
    errors: dict[str, list] = {}
    if not set(values) <= set(Diet.values):
        errors["diets"] = [_("Régime inconnu.")]
    text = (allergies or "").strip()
    if len(text) > ALLERGIES_MAX_LENGTH:
        errors["allergies"] = [_("200 caractères au plus.")]
    if not values and not text:
        errors["diets"] = [_("Indiquez un régime ou une allergie, ou retirez la déclaration.")]
    if errors:
        raise Invalid(fields=errors)
    declaration, _created = DietaryDeclaration.objects.update_or_create(
        edition=edition,
        user=user,
        defaults={"diets": values, "allergies": text, "consented_at": timezone.now()},
    )
    # Le journal garde l'acte, jamais le contenu (donnée sensible).
    record("dietary.declared", actor=actor, edition=edition, obj=declaration)
    return declaration


@transaction.atomic
def withdraw(edition: Edition, user: User, *, actor: Actor) -> None:
    """RG-23 : retrait du consentement, la déclaration est effacée."""
    declaration = declaration_of(edition, user)
    if declaration is not None:
        record("dietary.withdrawn", actor=actor, edition=edition, obj=declaration)
        declaration.delete()


def counts(declarations: Iterable[DietaryDeclaration]) -> dict[str, Any]:
    """Effectifs agrégés : par régime, et nombre de personnes avec une allergie."""
    by_diet: Counter[str] = Counter()
    allergies = 0
    for declaration in declarations:
        by_diet.update(declaration.diets)
        if declaration.allergies:
            allergies += 1
    return {"by_diet": {diet: by_diet.get(diet, 0) for diet in Diet.values}, "allergies": allergies}


def summary(edition: Edition) -> dict[str, Any]:
    declarations = list(DietaryDeclaration.objects.filter(edition=edition))
    return {"declarations": len(declarations), **counts(declarations)}


def nominative_rows(edition: Edition) -> tuple[list[str], list[list[Any]]]:
    """Liste nominative (export journalisé, réauthentification : vue)."""
    from django.utils.translation import gettext

    from apps.accounts.services.invitations import display_name

    header = [gettext("Nom"), gettext("Régimes"), gettext("Allergies")]
    rows = [
        [
            display_name(row.user),
            ", ".join(str(Diet(diet).label) for diet in row.diets),
            row.allergies,
        ]
        for row in DietaryDeclaration.objects.filter(edition=edition)
        .select_related("user__profile")
        .order_by("user__profile__last_name", "user__profile__first_name", "id")
    ]
    return header, rows


def erase_after_edition(dry_run: bool, now) -> int:
    """Tâche de conservation (RG-23, N15) : déclarations des éditions archivées ou finies
    depuis 30 jours, effacées."""
    rows = DietaryDeclaration.objects.filter(retention_filter(now))
    count = rows.count()
    if not dry_run and count:
        rows.delete()
    return count
