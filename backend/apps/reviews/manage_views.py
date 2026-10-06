"""Évaluation dans la gestion (``/v1/manage/editions/{edition_id}/…``, plan L4 §4).

``ManageViewSet`` : 401 → 404 → 403, 2FA. Grilles : lecture ``edition.read``, écriture
``grids.write`` (``ADMIN``, ``CHAIR``, ``SC_CHAIR``).
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability
from apps.conferences.models import SubmissionType
from apps.core.actor import Actor
from apps.core.errors import Invalid
from apps.reviews.models import EvaluationGrid
from apps.reviews.serializers import GridCreateSerializer, GridSerializer, GridUpdateSerializer
from apps.reviews.services import grids

C = Capability


class GridViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ManageViewSet):
    queryset = EvaluationGrid.objects.select_related("submission_type").prefetch_related("criteria")
    serializer_class = GridSerializer
    lookup_url_kwarg = "grid_id"
    pagination_class = None
    filter_backends = ()
    required_capabilities = {
        "list": C.EDITION_READ,
        "retrieve": C.EDITION_READ,
        "create": C.GRIDS_WRITE,
        "partial_update": C.GRIDS_WRITE,
        "destroy": C.GRIDS_WRITE,
        "duplicate": C.GRIDS_WRITE,
    }

    def get_queryset(self):
        return super().get_queryset().order_by("submission_type_id", "-version", "id")

    def _grid(self, grid_id: int) -> EvaluationGrid:
        return get_object_or_404(self.get_queryset(), pk=grid_id)

    @extend_schema(operation_id="manage_grids_list")
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(operation_id="manage_grid_retrieve")
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_grid_create",
        request=GridCreateSerializer,
        responses={201: GridSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = GridCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        submission_type = None
        if data.get("submission_type"):
            submission_type = SubmissionType.objects.filter(
                edition=self.edition, code=data["submission_type"]
            ).first()
            if submission_type is None:
                raise Invalid(fields={"submission_type": ["Code inconnu pour cette édition."]})
        grid = grids.create_grid(
            self.edition,
            name=data["name"],
            submission_type=submission_type,
            scale_min=data["scale_min"],
            scale_max=data["scale_max"],
            criteria=data.get("criteria"),
            actor=Actor.from_request(request),
        )
        return Response(GridSerializer(self._grid(grid.pk)).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_grid_update",
        request=GridUpdateSerializer,
        responses={200: GridSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, grid_id: int) -> Response:
        grid = self._grid(grid_id)
        serializer = GridUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        criteria = data.pop("criteria", None)
        grids.update_grid(grid, data, criteria=criteria, actor=Actor.from_request(request))
        return Response(GridSerializer(self._grid(grid_id)).data)

    @extend_schema(operation_id="manage_grid_delete", responses={204: None})
    def destroy(self, request: Request, edition_id: int, grid_id: int) -> Response:
        grids.delete_grid(self._grid(grid_id), actor=Actor.from_request(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_grid_duplicate", request=None, responses={201: GridSerializer}
    )
    def duplicate(self, request: Request, edition_id: int, grid_id: int) -> Response:
        """RG-05 : nouvelle version modifiable d'une grille (verrouillée ou non)."""
        grid = grids.duplicate_grid(self._grid(grid_id), actor=Actor.from_request(request))
        return Response(GridSerializer(self._grid(grid.pk)).data, status=status.HTTP_201_CREATED)
