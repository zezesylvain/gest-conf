"""Segments des envois groupés lus dans le **programme publié** (plan L8, N11) : jamais dans
le brouillon (I7)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User


def _people(edition, roles: frozenset[str]):
    from apps.program.services.publication import latest_publication, passages

    publication = latest_publication(edition)
    if publication is None:
        return User.objects.none()
    ids = {
        int(key.partition(":")[2])
        for key, items in passages(publication.snapshot).items()
        if key.startswith("user:") and any(item.role in roles for item in items)
    }
    return User.objects.filter(pk__in=ids)


def presenters(edition):
    return _people(edition, frozenset({"presenter", "speaker"}))


def session_chairs(edition):
    return _people(edition, frozenset({"chair"}))


def register_program_segments() -> None:
    from apps.communications.segments import Segment, register_segment

    register_segment(Segment("program.presenters", _("Présentateurs au programme"), presenters, 20))
    register_segment(
        Segment("program.session_chairs", _("Présidents de séance"), session_chairs, 21)
    )
