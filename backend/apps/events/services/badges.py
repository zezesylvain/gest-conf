"""Badges des inscriptions confirmées (plan L7, K3).

Produits à la demande, jamais stockés ; téléchargement par le CO journalisé (nombre,
catégorie, lot), jamais le jeton.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from django.http import Http404

from apps.core.audit import record
from apps.events import badges
from apps.registrations.models import Registration, RegistrationStatus

if TYPE_CHECKING:
    from apps.conferences.models import Edition
    from apps.core.actor import Actor


def _colors(edition: Edition) -> dict[int, str]:
    """Couleur de chaque catégorie : la sienne, sinon celle de la palette selon son rang."""
    categories = edition.registration_categories.order_by("position", "id")
    return {
        category.pk: category.badge_color or badges.default_color(index)
        for index, category in enumerate(categories)
    }


def badge_data(
    registration: Registration, colors: dict[int, str] | None = None
) -> badges.BadgeData:
    if registration.status != RegistrationStatus.CONFIRMED or not registration.qr_token:
        raise Http404
    colors = colors if colors is not None else _colors(registration.edition)
    profile = getattr(registration.user, "profile", None)
    name = ""
    if profile is not None:
        name = f"{profile.first_name} {profile.last_name}".strip()
    return badges.BadgeData(
        edition_title=registration.edition.title_fr,
        name=name or registration.reference,
        institution=profile.institution if profile is not None else "",
        country=profile.country if profile is not None else "",
        category_label=registration.category.label_fr,
        category_label_en=registration.category.label_en,
        color=colors.get(registration.category_id, badges.default_color(0)),
        token=registration.qr_token,
        reference=registration.reference,
    )


def single_badge(registration: Registration) -> bytes:
    return badges.render_single(badge_data(registration))


def committee_selection(edition: Edition, *, category: str = ""):
    """Inscriptions confirmées, par nom puis prénom (ordre de classement des badges)."""
    rows = (
        Registration.objects.filter(
            edition=edition, status=RegistrationStatus.CONFIRMED, qr_token__isnull=False
        )
        .select_related("edition", "category", "user__profile")
        .order_by("user__profile__last_name", "user__profile__first_name", "id")
    )
    if category:
        rows = rows.filter(category__code=category)
    return rows


def batches(edition: Edition, *, category: str = "") -> dict[str, int]:
    count = committee_selection(edition, category=category).count()
    return {
        "count": count,
        "batch_size": badges.BATCH_SIZE,
        "batches": math.ceil(count / badges.BATCH_SIZE),
    }


def committee_badges(
    edition: Edition, *, category: str = "", batch: int = 1, actor: Actor
) -> bytes:
    """Lot ``batch`` (à partir de 1) de 200 badges au plus, en planches A4."""
    start = (batch - 1) * badges.BATCH_SIZE
    rows = list(committee_selection(edition, category=category)[start : start + badges.BATCH_SIZE])
    if not rows:
        raise Http404
    colors = _colors(edition)
    content = badges.render_sheets(
        [badge_data(row, colors) for row in rows], f"Badges {edition.code}"
    )
    record(
        "registrations.badges_downloaded",
        actor=actor,
        edition=edition,
        after={"count": len(rows), "category": category, "batch": batch},
    )
    return content


def committee_single_badge(registration: Registration, *, actor: Actor) -> bytes:
    content = single_badge(registration)
    record(
        "registrations.badge_downloaded",
        actor=actor,
        edition=registration.edition,
        obj=registration,
    )
    return content
