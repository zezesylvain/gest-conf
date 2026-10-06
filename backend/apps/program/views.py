"""Routes du programme dans la gestion (``v1/manage/editions/{id}/program/…``, plan L5 §4)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.program.serializers import ProgramSettingsSerializer
from apps.program.services import settings as program_settings


class ProgramSettingsViewSet(ManageViewSet):
    """``…/program/settings`` : paramètres du programme (I17). Lecture ``program.read``,
    écriture ``program.write`` (CO « programme », administrateur ; I1)."""

    serializer_class = ProgramSettingsSerializer
    required_capabilities = {"retrieve": C.PROGRAM_READ, "partial_update": C.PROGRAM_WRITE}

    @extend_schema(operation_id="manage_program_settings_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(ProgramSettingsSerializer(self.edition).data)

    @extend_schema(operation_id="manage_program_settings_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        serializer = ProgramSettingsSerializer(self.edition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        edition = program_settings.update_program_settings(
            self.edition, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(ProgramSettingsSerializer(edition).data)
