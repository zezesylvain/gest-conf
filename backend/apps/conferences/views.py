"""Paramétrage de l'édition (``/v1/manage/editions/…``) et édition publique (plan L1 §9.3).

Toutes les routes d'une édition héritent de ``ManageViewSet`` : édition chargée avant les
permissions, capacité exigée par action, 2FA (L1.6). Les écritures passent par les
services, qui auditent et refusent une édition archivée.
"""

from __future__ import annotations

from django.db.models import QuerySet
from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability
from apps.accounts.services.access import editions_with_roles
from apps.conferences import services
from apps.conferences.models import Edition, EditionStatus, KeyDate, SubmissionType, Track
from apps.conferences.serializers import (
    ConfidentialitySerializer,
    EditionSerializer,
    EditionStatusChangeSerializer,
    EditionSummarySerializer,
    KeyDateSerializer,
    KeyDateWriteSerializer,
    PublicEditionSerializer,
    SubmissionTypeSerializer,
    TrackSerializer,
)
from apps.core.actor import Actor

C = Capability


class ManageEditionListView(ListAPIView):
    """``GET /v1/manage/editions`` : sélecteur d'édition (§5.3, D3).

    Éditions où l'on détient au moins une capacité de gestion ; champs non sensibles ;
    **sans** 2FA (chaque édition l'exige ensuite). Seule vue de ``v1/manage/`` hors
    ``ManageViewSet`` (liste blanche du test de plateforme).
    """

    permission_classes = (IsAuthenticated,)
    serializer_class = EditionSummarySerializer
    pagination_class = None

    def get_queryset(self) -> QuerySet:
        if getattr(self, "swagger_fake_view", False):  # génération du schéma OpenAPI
            return Edition.objects.none()
        accesses = editions_with_roles(self.request.user)
        ids = [edition_id for edition_id, access in accesses.items() if access.capabilities]
        return Edition.objects.filter(pk__in=ids).order_by("-year", "id")

    @extend_schema(operation_id="manage_editions_list")
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class EditionViewSet(ManageViewSet):
    """``/v1/manage/editions/{edition_id}`` : informations générales (§6.1)."""

    required_capabilities = {"retrieve": C.EDITION_READ, "partial_update": C.EDITION_WRITE}
    serializer_class = EditionSerializer

    @extend_schema(operation_id="manage_edition_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(EditionSerializer(self.edition).data)

    @extend_schema(operation_id="manage_edition_update", request=EditionSerializer)
    def partial_update(self, request: Request, edition_id: int) -> Response:
        serializer = EditionSerializer(self.edition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        reason = data.pop("reason", "")
        edition = services.update_edition(
            self.edition, data, actor=Actor.from_request(request), reason=reason
        )
        return Response(EditionSerializer(edition).data)


class EditionStatusViewSet(ManageViewSet):
    """``POST …/status`` : publication (ADMIN, CHAIR) ou archivage (ADMIN), avec
    réauthentification récente (§6.3, D12)."""

    serializer_class = EditionStatusChangeSerializer
    required_capabilities = {"create": C.EDITION_PUBLISH}

    def get_permissions(self):
        return [*super().get_permissions(), RecentAuthRequired()]

    def check_permissions(self, request: Request) -> None:
        # La capacité dépend du statut visé : archivage réservé à l'ADMIN.
        target = request.data.get("status") if isinstance(request.data, dict) else None
        if target == EditionStatus.ARCHIVED:
            self.required_capabilities = {"create": C.EDITION_ARCHIVE}
        super().check_permissions(request)

    @extend_schema(
        operation_id="manage_edition_status",
        request=EditionStatusChangeSerializer,
        responses={200: EditionSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = EditionStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edition = services.set_edition_status(
            self.edition,
            serializer.validated_data["status"],
            actor=Actor.from_request(request),
            reason=serializer.validated_data["reason"],
        )
        return Response(EditionSerializer(edition).data)


class ConfidentialityViewSet(ManageViewSet):
    """``…/confidentiality`` : double aveugle, relecteurs par soumission (§6.1).
    Écriture : réauthentification récente, audit classé critique."""

    serializer_class = ConfidentialitySerializer
    required_capabilities = {"retrieve": C.EDITION_READ, "partial_update": C.EDITION_WRITE}

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "partial_update":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(operation_id="manage_confidentiality_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(ConfidentialitySerializer(self.edition).data)

    @extend_schema(operation_id="manage_confidentiality_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        serializer = ConfidentialitySerializer(self.edition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        reason = data.pop("reason", "")
        edition = services.update_confidentiality(
            self.edition, data, actor=Actor.from_request(request), reason=reason
        )
        return Response(ConfidentialitySerializer(edition).data)


class _EditionChildViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    ManageViewSet,
):
    """Liste, détail, création, modification, suppression d'un élément de l'édition."""

    required_capabilities = {
        "list": C.EDITION_READ,
        "retrieve": C.EDITION_READ,
        "create": C.EDITION_WRITE,
        "partial_update": C.EDITION_WRITE,
        "destroy": C.EDITION_WRITE,
    }
    pagination_class = None
    lookup_url_kwarg = "item_id"
    write_serializer_class = None

    def _write_data(self, request: Request, *, partial: bool) -> dict:
        serializer_class = self.write_serializer_class or self.get_serializer_class()
        serializer = serializer_class(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        return dict(serializer.validated_data)

    def create(self, request: Request, edition_id: int) -> Response:
        instance = self.create_item(self._write_data(request, partial=False), request)
        return Response(self.get_serializer(instance).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        instance = self.update_item(
            self.get_object(), self._write_data(request, partial=True), request
        )
        return Response(self.get_serializer(instance).data)

    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        self.delete_item(self.get_object(), request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TrackViewSet(_EditionChildViewSet):
    queryset = Track.objects.select_related("edition").order_by("position", "id")
    serializer_class = TrackSerializer

    def create_item(self, data, request):
        return services.create_track(self.edition, data, actor=Actor.from_request(request))

    def update_item(self, instance, data, request):
        return services.update_track(instance, data, actor=Actor.from_request(request))

    def delete_item(self, instance, request):
        services.delete_track(instance, actor=Actor.from_request(request))


class SubmissionTypeViewSet(_EditionChildViewSet):
    queryset = SubmissionType.objects.select_related("edition").order_by("position", "id")
    serializer_class = SubmissionTypeSerializer

    def create_item(self, data, request):
        return services.create_submission_type(
            self.edition, data, actor=Actor.from_request(request)
        )

    def update_item(self, instance, data, request):
        return services.update_submission_type(instance, data, actor=Actor.from_request(request))

    def delete_item(self, instance, request):
        services.delete_submission_type(instance, actor=Actor.from_request(request))


class KeyDateViewSet(_EditionChildViewSet):
    """Dates clés : saisie ``at_local`` à l'heure de l'édition (D13)."""

    queryset = KeyDate.objects.select_related("edition").order_by("at", "position", "id")
    serializer_class = KeyDateSerializer
    write_serializer_class = KeyDateWriteSerializer

    @extend_schema(request=KeyDateWriteSerializer, responses={201: KeyDateSerializer})
    def create(self, request: Request, edition_id: int) -> Response:
        return super().create(request, edition_id)

    @extend_schema(request=KeyDateWriteSerializer, responses={200: KeyDateSerializer})
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        return super().partial_update(request, edition_id, item_id)

    def create_item(self, data, request):
        return services.create_key_date(self.edition, data, actor=Actor.from_request(request))

    def update_item(self, instance, data, request):
        return services.update_key_date(instance, data, actor=Actor.from_request(request))

    def delete_item(self, instance, request):
        services.delete_key_date(instance, actor=Actor.from_request(request))


class PublicCurrentEditionView(APIView):
    """``GET /v1/public/editions/current`` : édition courante publiée (§9.3), sinon 404.

    Brouillons et dates internes invisibles. Sert au portail (L2) et au test de fumée.
    """

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="public_current_edition", responses={200: PublicEditionSerializer}, auth=[]
    )
    def get(self, request: Request) -> Response:
        edition = services.current_public_edition()
        if edition is None:
            raise Http404
        response = Response(PublicEditionSerializer(edition).data)
        response["Cache-Control"] = "public, max-age=300"
        return response
