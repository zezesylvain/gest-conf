"""Routes du jour J et des attestations (plan L7 §4).

Gestion (``v1/manage/editions/{id}/…``, 2FA) :

- signature du signataire (K18), lue et écrite par lui seul (``signature.manage``),
  réauthentification pour l'écrire ;
- pointage à l'accueil (K4, K5) : lecture du badge, liste hors ligne et synchronisation
  (``checkin.scan``) ; saisie manuelle, liste, annulation et export (``checkin.manage``) ;
- badges (K3, ``registrations.read``) et remplacement d'un badge perdu (K2,
  ``checkin.manage``).

Participant : ``GET /v1/registrations/{id}/badge``, son badge, dès la confirmation.
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text
from apps.events.models import Checkin, CheckinMethod
from apps.events.serializers import (
    BadgeBatchesSerializer,
    BundleSerializer,
    CheckinListItemSerializer,
    CheckinResultSerializer,
    CheckinSerializer,
    CheckinSummarySerializer,
    ManualRequestSerializer,
    ReasonSerializer,
    ScanRequestSerializer,
    SignatureImageUploadSerializer,
    SignatureSerializer,
    SyncRequestSerializer,
    SyncResponseSerializer,
    checkin_data,
    person_data,
    result_data,
    signature_data,
)
from apps.events.services import badges as badge_services
from apps.events.services import checkin as checkin_services
from apps.events.services import signatures
from apps.registrations.models import Registration
from apps.registrations.services import orders


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


# --- Pointage à l'accueil (K4, K5) ---------------------------------------------------------------


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "private, no-store"
    return response


class CheckinViewSet(ManageViewSet):
    """``…/checkin/…`` : pointage à l'accueil."""

    # Pour le schéma (liste paginée) ; les actions lisent par le service, filtré par édition.
    queryset = Checkin.objects.none()
    serializer_class = CheckinResultSerializer
    required_capabilities = {
        "scan": C.CHECKIN_SCAN,
        "bundle": C.CHECKIN_SCAN,
        "sync": C.CHECKIN_SCAN,
        "summary": C.CHECKIN_SCAN,
        "manual": C.CHECKIN_MANAGE,
        "list": C.CHECKIN_MANAGE,
        "cancel": C.CHECKIN_MANAGE,
        "export": C.CHECKIN_MANAGE,
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "export":
            # Données personnelles en masse : réauthentification, comme les exports de L6.
            permissions.append(RecentAuthRequired())
        return permissions

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    @extend_schema(
        operation_id="manage_checkin_scan",
        request=ScanRequestSerializer,
        responses={200: CheckinResultSerializer},
    )
    def scan(self, request: Request, edition_id: int) -> Response:
        """Lecture du QR d'un badge : pointé, déjà pointé, ou refus explicite (K4)."""
        serializer = ScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = checkin_services.check_in(
            self.edition,
            token=data["token"],
            method=CheckinMethod.SCAN,
            device=data["device"],
            idempotency_key=data["idempotency_key"],
            actor=self.actor(),
        )
        return _no_store(Response(CheckinResultSerializer(result_data(result)).data))

    @extend_schema(
        operation_id="manage_checkin_manual",
        request=ManualRequestSerializer,
        responses={200: CheckinResultSerializer},
    )
    def manual(self, request: Request, edition_id: int) -> Response:
        """Saisie de la référence (caméra en panne, badge oublié) : ``checkin.manage``."""
        serializer = ManualRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = checkin_services.check_in(
            self.edition,
            reference=data["reference"],
            method=CheckinMethod.MANUAL,
            device=data["device"],
            idempotency_key=data["idempotency_key"],
            actor=self.actor(),
        )
        return _no_store(Response(CheckinResultSerializer(result_data(result)).data))

    @extend_schema(operation_id="manage_checkin_bundle", responses={200: BundleSerializer})
    def bundle(self, request: Request, edition_id: int) -> Response:
        """Liste hors ligne (K5) : empreintes, références, noms, catégories ; journalisée."""
        data = checkin_services.offline_bundle(self.edition, actor=self.actor())
        return _no_store(Response(BundleSerializer(data).data))

    @extend_schema(
        operation_id="manage_checkin_sync",
        request=SyncRequestSerializer,
        responses={200: SyncResponseSerializer},
    )
    def sync(self, request: Request, edition_id: int) -> Response:
        """File hors ligne (K5) : chaque pointage est revérifié ; rejouable sans doublon."""
        serializer = SyncRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        results = checkin_services.synchronize(
            self.edition,
            data["items"],
            device=data["device"],
            may_enter_manually=self.access.has(C.CHECKIN_MANAGE),
            actor=self.actor(),
        )
        payload = {"results": [result_data(result) for result in results]}
        return _no_store(Response(SyncResponseSerializer(payload).data))

    @extend_schema(operation_id="manage_checkin_summary", responses={200: CheckinSummarySerializer})
    def summary(self, request: Request, edition_id: int) -> Response:
        return Response(CheckinSummarySerializer(checkin_services.summary(self.edition)).data)

    @extend_schema(
        operation_id="manage_checkin_list",
        parameters=[
            OpenApiParameter("q", str, description="Nom ou référence."),
            OpenApiParameter("cancelled", bool, description="Inclure les pointages annulés."),
        ],
        responses={200: CheckinListItemSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = checkin_services.checkins(
            self.edition,
            query=request.query_params.get("q", ""),
            include_cancelled=request.query_params.get("cancelled") in ("1", "true"),
        )
        page = self.paginate_queryset(rows)
        data = [
            {**checkin_data(row), "registration": person_data(row.registration)} for row in page
        ]
        return self.get_paginated_response(CheckinListItemSerializer(data, many=True).data)

    @extend_schema(
        operation_id="manage_checkin_cancel",
        request=ReasonSerializer,
        responses={200: CheckinSerializer},
    )
    def cancel(self, request: Request, edition_id: int, checkin_id: int) -> Response:
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        checkin = Checkin.objects.filter(edition=self.edition, pk=checkin_id).first()
        if checkin is None:
            raise Http404
        checkin = checkin_services.cancel_checkin(
            checkin, reason=serializer.validated_data["reason"], actor=self.actor()
        )
        return Response(CheckinSerializer(checkin_data(checkin)).data)

    @extend_schema(
        operation_id="manage_checkin_export",
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """Présences à l'accueil en CSV (pointages non annulés), journalisé."""
        rows = list(checkin_services.checkins(self.edition))
        content = csv_text(
            [str(item) for item in checkin_services.EXPORT_HEADER],
            checkin_services.export_rows(rows),
        )
        record(
            "checkin.exported",
            actor=self.actor(),
            edition=self.edition,
            after={"count": len(rows)},
        )
        return csv_response(content, f"presences-{self.edition.code}-{timezone.now():%Y%m%d}.csv")


# --- Badges (K3) et badge perdu (K2) -------------------------------------------------------------


def pdf_response(content: bytes, filename: str) -> HttpResponse:
    response = HttpResponse(content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-Content-Type-Options"] = "nosniff"
    # Le badge porte un titre d'accès : jamais en cache (K3).
    response["Cache-Control"] = "private, no-store"
    return response


def _batch(request: Request) -> int:
    value = request.query_params.get("batch", "1")
    if not value.isdigit() or int(value) < 1:
        raise Invalid(fields={"batch": [_("Numéro de lot attendu (1, 2…).")]})
    return int(value)


CATEGORY_PARAMETER = OpenApiParameter("category", str, description="Code de catégorie.")


class BadgeViewSet(ManageViewSet):
    """``…/registrations/badges`` (lots), ``…/registrations/{id}/badge`` (un badge) et
    ``…/registrations/{id}/regenerate-token`` (badge perdu)."""

    serializer_class = BadgeBatchesSerializer
    required_capabilities = {
        "batches": C.REGISTRATIONS_READ,
        "sheets": C.REGISTRATIONS_READ,
        "single": C.REGISTRATIONS_READ,
        "regenerate": C.CHECKIN_MANAGE,
    }

    def registration(self, registration_id: int) -> Registration:
        found = (
            Registration.objects.filter(edition=self.edition, pk=registration_id)
            .select_related("edition", "category", "user__profile")
            .first()
        )
        if found is None:
            raise Http404
        return found

    @extend_schema(
        operation_id="manage_badges_batches",
        parameters=[CATEGORY_PARAMETER],
        responses={200: BadgeBatchesSerializer},
    )
    def batches(self, request: Request, edition_id: int) -> Response:
        data = badge_services.batches(
            self.edition, category=request.query_params.get("category", "")
        )
        return Response(BadgeBatchesSerializer(data).data)

    @extend_schema(
        operation_id="manage_badges_sheets",
        parameters=[
            CATEGORY_PARAMETER,
            OpenApiParameter("batch", int, description="Lot de 200 badges, à partir de 1."),
        ],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def sheets(self, request: Request, edition_id: int) -> HttpResponse:
        batch = _batch(request)
        content = badge_services.committee_badges(
            self.edition,
            category=request.query_params.get("category", ""),
            batch=batch,
            actor=Actor.from_request(request),
        )
        return pdf_response(content, f"badges-{self.edition.code}-{batch}.pdf")

    @extend_schema(
        operation_id="manage_badge_single",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def single(self, request: Request, edition_id: int, registration_id: int) -> HttpResponse:
        registration = self.registration(registration_id)
        content = badge_services.committee_single_badge(
            registration, actor=Actor.from_request(request)
        )
        return pdf_response(content, f"badge-{registration.reference}.pdf")

    @extend_schema(
        operation_id="manage_badge_regenerate",
        request=ReasonSerializer,
        responses={204: None},
    )
    def regenerate(self, request: Request, edition_id: int, registration_id: int) -> Response:
        """Badge perdu : nouveau jeton, l'ancien badge est refusé (« badge remplacé »)."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orders.regenerate_qr_token(
            self.registration(registration_id),
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return Response(status=204)


class MyBadgeView(APIView):
    """``GET /v1/registrations/{id}/badge`` : le badge du participant (A6), dès la
    confirmation ; 404 sinon."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="registrations_badge",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, registration_id: int) -> HttpResponse:
        registration = (
            Registration.objects.filter(user=request.user, pk=registration_id)
            .select_related("edition", "category", "user__profile")
            .first()
        )
        if registration is None:
            raise Http404
        return pdf_response(
            badge_services.single_badge(registration), f"badge-{registration.reference}.pdf"
        )
