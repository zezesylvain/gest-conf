"""Routes du jour J et des attestations (plan L7 §4).

Gestion (``v1/manage/editions/{id}/…``, 2FA) : signature du signataire (K18), lue et écrite
par lui seul (``signature.manage``), réauthentification pour l'écrire.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.events.serializers import (
    SignatureImageUploadSerializer,
    SignatureSerializer,
    signature_data,
)
from apps.events.services import signatures


class _SignatureBase(ManageViewSet):
    """Signature du compte connecté (K18) : ``signature.manage`` ; écritures avec une
    réauthentification récente (D12), comme une attribution de rôle."""

    writes: tuple[str, ...] = ()

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in self.writes:
            permissions.append(RecentAuthRequired())
        return permissions


class SignatureViewSet(_SignatureBase):
    """``…/signature`` : nom affiché et fonction (FR, EN)."""

    serializer_class = SignatureSerializer
    required_capabilities = {"retrieve": C.SIGNATURE_MANAGE, "partial_update": C.SIGNATURE_MANAGE}
    writes = ("partial_update",)

    @extend_schema(operation_id="manage_signature_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        signature = signatures.signature_of(self.edition, request.user)
        return Response(SignatureSerializer(signature_data(signature)).data)

    @extend_schema(operation_id="manage_signature_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        current = signature_data(signatures.signature_of(self.edition, request.user))
        serializer = SignatureSerializer(data={**current, **request.data})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = signatures.update_details(
            self.edition,
            request.user,
            display_name=data["display_name"],
            title_fr=data["title_fr"],
            title_en=data["title_en"],
            actor=Actor.from_request(request),
        )
        return Response(SignatureSerializer(signature_data(signature)).data)


class SignatureImageViewSet(_SignatureBase):
    """``…/signature/image`` : dépôt (PNG ou JPEG, réencodé en PNG) et aperçu."""

    serializer_class = SignatureImageUploadSerializer
    parser_classes = (MultiPartParser,)
    required_capabilities = {"image": C.SIGNATURE_MANAGE, "upload_image": C.SIGNATURE_MANAGE}
    writes = ("upload_image",)
    throttle_scope = "signature_upload"

    def get_throttles(self):
        # Limite sur le seul dépôt : la même vue sert l'aperçu.
        return super().get_throttles() if self.action == "upload_image" else []

    @extend_schema(
        operation_id="manage_signature_image_upload",
        request={"multipart/form-data": SignatureImageUploadSerializer},
        responses={200: SignatureSerializer},
    )
    def upload_image(self, request: Request, edition_id: int) -> Response:
        serializer = SignatureImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        # Lecture bornée : au-delà de la limite, le service refuse sans tout charger.
        data = upload.read(signatures.IMAGE_MAX_BYTES + 1)
        signature = signatures.upload_image(
            self.edition, request.user, data=data, actor=Actor.from_request(request)
        )
        return Response(SignatureSerializer(signature_data(signature)).data)

    @extend_schema(
        operation_id="manage_signature_image",
        responses={(200, "image/png"): OpenApiTypes.BINARY},
    )
    def image(self, request: Request, edition_id: int) -> HttpResponse:
        """Image déposée, pour l'aperçu du signataire (règle n° 8 : endpoint authentifié)."""
        signature = signatures.signature_of(self.edition, request.user)
        if signature is None or not signature.image_storage_name:
            raise Http404
        try:
            data = signatures.image_bytes(signature)
        except FileNotFoundError as error:
            raise Http404 from error
        response = HttpResponse(data, content_type="image/png")
        response["Content-Disposition"] = 'inline; filename="signature.png"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
