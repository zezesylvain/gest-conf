"""Permissions du jour J (plan L7, K1, K7, K8)."""

from __future__ import annotations

from typing import Any

from rest_framework.request import Request

from apps.accounts.permissions import HasCapability


class CapabilityOrSessionChair(HasCapability):
    """Capacité de l'action, **ou** présidence de la session du chemin au programme publié,
    pour les seules actions listées dans ``view.chair_actions`` (K1 : le président de séance
    émarge ses sessions et marque leurs communications présentées, sans autre droit).

    Sans session dans le chemin (liste des sessions du jour), il suffit de présider une
    session publiée ; la vue ne lui montre alors que les siennes.
    """

    def has_permission(self, request: Request, view: Any) -> bool:
        if super().has_permission(request, view):
            return True
        if getattr(view, "action", None) not in getattr(view, "chair_actions", ()):
            return False
        access = getattr(view, "access", None)
        if access is None:
            return False
        from apps.events.services.attendance import chaired_session_ids

        chaired = chaired_session_ids(access.edition, request.user)
        session_id = view.kwargs.get("session_id")
        if session_id is None:
            return bool(chaired)
        return int(session_id) in chaired
