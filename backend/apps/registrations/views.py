"""Routes des inscriptions (plan L6 §4).

Gestion (``v1/manage/editions/{id}/registrations/…``) : lecture ``registrations.read``,
paramètres et tarifs ``pricing.write`` (J1). Chaque écriture passe par un service
(journal, verrou, édition archivée en lecture seule).
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.registrations.serializers import RegistrationSettingsSerializer
from apps.registrations.services import settings as registration_settings


class RegistrationSettingsViewSet(ManageViewSet):
    """``…/registrations/settings`` : devise, pays locaux, moyens et échéances, annulation."""

    serializer_class = RegistrationSettingsSerializer
    required_capabilities = {"retrieve": C.REGISTRATIONS_READ, "partial_update": C.PRICING_WRITE}

    @extend_schema(operation_id="manage_registration_settings_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        settings = registration_settings.registration_settings(self.edition)
        return Response(RegistrationSettingsSerializer(settings).data)

    @extend_schema(operation_id="manage_registration_settings_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        current = registration_settings.registration_settings(self.edition)
        serializer = RegistrationSettingsSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        settings = registration_settings.update_registration_settings(
            self.edition, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(RegistrationSettingsSerializer(settings).data)
