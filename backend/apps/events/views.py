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
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, MfaVerified, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text
from apps.events import signing
from apps.events.models import (
    Certificate,
    Checkin,
    CheckinMethod,
    DocumentNature,
    DocumentTemplate,
    InvitationLetter,
    LetterStatus,
)
from apps.events.permissions import CapabilityOrSessionChair
from apps.events.serializers import (
    BadgeBatchesSerializer,
    BundleSerializer,
    CertificateOverviewSerializer,
    CertificateSerializer,
    CertificateSettingsSerializer,
    CheckinListItemSerializer,
    CheckinResultSerializer,
    CheckinSerializer,
    CheckinSummarySerializer,
    CounterRequestSerializer,
    CounterResponseSerializer,
    DaySessionSerializer,
    DocumentTemplateSerializer,
    DocumentTemplateUpdateSerializer,
    ImageUploadSerializer,
    IssueRequestSerializer,
    IssueResponseSerializer,
    LetterRequestSerializer,
    ManageLetterDetailSerializer,
    ManageLetterSerializer,
    ManualRequestSerializer,
    MyCertificateSerializer,
    MyLetterSerializer,
    PublicVerificationSerializer,
    ReasonSerializer,
    ScanRequestSerializer,
    SessionScanRequestSerializer,
    SignatorySerializer,
    SignatureImageUploadSerializer,
    SignatureSerializer,
    SigningKeyUploadSerializer,
    SyncRequestSerializer,
    SyncResponseSerializer,
    certificate_data,
    certificate_settings_data,
    checkin_data,
    manage_letter_data,
    my_certificate_data,
    my_letter_data,
    person_data,
    result_data,
    signatory_data,
    signature_data,
    template_data,
)
from apps.events.services import attendance, certificates, counter, letters, signatures
from apps.events.services import badges as badge_services
from apps.events.services import checkin as checkin_services
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


# --- Émargement des sessions et communications présentées (K7, K8) -----------------------


class DaySessionViewSet(ManageViewSet):
    """``…/day/sessions/…`` : sessions du programme publié, émargement, « présentée ».

    Capacité de l'action, **ou** présidence de la session au programme publié pour les
    actions de ``chair_actions`` (``CapabilityOrSessionChair``)."""

    queryset = Checkin.objects.none()
    serializer_class = DaySessionSerializer
    permission_classes = (IsAuthenticated, CapabilityOrSessionChair, MfaVerified)
    required_capabilities = {
        "sessions": C.CHECKIN_SCAN,
        "attendance": C.CHECKIN_MANAGE,
        "attendance_scan": C.CHECKIN_SCAN,
        "attendance_export": C.CHECKIN_MANAGE,
        "presented": C.PROGRAM_WRITE,
        "unpresented": C.PROGRAM_WRITE,
    }
    chair_actions = ("sessions", "attendance", "attendance_scan", "presented")

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "attendance_export":
            permissions.append(RecentAuthRequired())
        return permissions

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def session(self, session_id: int) -> dict:
        return attendance.published_session(self.edition, session_id)

    @extend_schema(
        operation_id="manage_day_sessions", responses={200: DaySessionSerializer(many=True)}
    )
    def sessions(self, request: Request, edition_id: int) -> Response:
        """Sessions publiées (toutes, ou celles que préside le compte s'il n'a pas
        ``checkin.scan``)."""
        chaired = attendance.chaired_session_ids(self.edition, request.user)
        only = None if self.access.has(C.CHECKIN_SCAN) else chaired
        rows = [
            {**item, "chaired": item["id"] in chaired}
            for item in attendance.day_sessions(self.edition, only=only)
        ]
        return Response(DaySessionSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="manage_day_attendance",
        parameters=[OpenApiParameter("q", str, description="Nom ou référence.")],
        responses={200: CheckinListItemSerializer(many=True)},
    )
    def attendance(self, request: Request, edition_id: int, session_id: int) -> Response:
        """Présents pointés à l'entrée de la session (K7)."""
        self.session(session_id)
        rows = checkin_services.checkins(
            self.edition, query=request.query_params.get("q", ""), session_id=session_id
        )
        page = self.paginate_queryset(rows)
        data = [
            {**checkin_data(row), "registration": person_data(row.registration)} for row in page
        ]
        return self.get_paginated_response(CheckinListItemSerializer(data, many=True).data)

    @extend_schema(
        operation_id="manage_day_attendance_scan",
        request=SessionScanRequestSerializer,
        responses={200: CheckinResultSerializer},
    )
    def attendance_scan(self, request: Request, edition_id: int, session_id: int) -> Response:
        """Badge lu à l'entrée de la session : vaut présence, même sans pointage d'accueil."""
        self.session(session_id)
        serializer = SessionScanRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = checkin_services.check_in(
            self.edition,
            token=data["token"],
            method=CheckinMethod.SCAN,
            device=data["device"],
            idempotency_key=data["idempotency_key"],
            session_id=session_id,
            actor=self.actor(),
        )
        return _no_store(Response(CheckinResultSerializer(result_data(result)).data))

    @extend_schema(
        operation_id="manage_day_attendance_export",
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def attendance_export(self, request: Request, edition_id: int, session_id: int) -> HttpResponse:
        self.session(session_id)
        rows = list(checkin_services.checkins(self.edition, session_id=session_id))
        content = csv_text(
            [str(item) for item in checkin_services.EXPORT_HEADER],
            checkin_services.export_rows(rows),
        )
        record(
            "checkin.session_exported",
            actor=self.actor(),
            edition=self.edition,
            after={"session": session_id, "count": len(rows)},
        )
        return csv_response(content, f"presences-{self.edition.code}-session-{session_id}.csv")

    @extend_schema(
        operation_id="manage_day_presented",
        request=None,
        responses={200: DaySessionSerializer},
    )
    def presented(
        self, request: Request, edition_id: int, session_id: int, slot_id: int
    ) -> Response:
        """Communication présentée (K8) : ``SCHEDULED → PRESENTED`` par le workflow."""
        attendance.mark_presented(self.edition, session_id, slot_id, actor=self.actor())
        return self.session_response(request, session_id)

    @extend_schema(
        operation_id="manage_day_unpresented",
        request=ReasonSerializer,
        responses={200: DaySessionSerializer},
    )
    def unpresented(
        self, request: Request, edition_id: int, session_id: int, slot_id: int
    ) -> Response:
        """Correction (``PRESENTED → SCHEDULED``) : ``program.write``, motif obligatoire."""
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance.unmark_presented(
            self.edition,
            session_id,
            slot_id,
            reason=serializer.validated_data["reason"],
            actor=self.actor(),
        )
        return self.session_response(request, session_id)

    def session_response(self, request: Request, session_id: int) -> Response:
        chaired = attendance.chaired_session_ids(self.edition, request.user)
        row = attendance.day_sessions(self.edition, only={session_id})[0]
        return Response(DaySessionSerializer({**row, "chaired": session_id in chaired}).data)


# --- Attestations (K9 à K11, K18, K19) --------------------------------------------------------


class _CertificatesBase(ManageViewSet):
    """``certificates.manage`` partout ; écritures sous réauthentification récente (D12)."""

    writes: tuple[str, ...] = ()

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in self.writes:
            permissions.append(RecentAuthRequired())
        return permissions

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def settings_response(self) -> Response:
        current = certificates.certificate_settings(self.edition)
        return Response(CertificateSettingsSerializer(certificate_settings_data(current)).data)


class CertificateSettingsViewSet(_CertificatesBase):
    """``…/certificates/settings`` : mode de signature, attestation d'évaluation, disposition."""

    serializer_class = CertificateSettingsSerializer
    required_capabilities = {
        "retrieve": C.CERTIFICATES_MANAGE,
        "partial_update": C.CERTIFICATES_MANAGE,
    }
    writes = ("partial_update",)

    @extend_schema(operation_id="manage_certificate_settings_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return self.settings_response()

    @extend_schema(operation_id="manage_certificate_settings_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        serializer = CertificateSettingsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        certificates.update_settings(
            self.edition, dict(serializer.validated_data), actor=self.actor()
        )
        return self.settings_response()


class CertificateFilesViewSet(_CertificatesBase):
    """``…/certificates/settings/header`` (en-tête du modèle officiel) et
    ``…/certificates/settings/signing-key`` (certificat PAdES de l'institution)."""

    serializer_class = CertificateSettingsSerializer
    parser_classes = (MultiPartParser,)
    required_capabilities = {
        "header": C.CERTIFICATES_MANAGE,
        "upload_header": C.CERTIFICATES_MANAGE,
        "delete_header": C.CERTIFICATES_MANAGE,
        "upload_key": C.CERTIFICATES_MANAGE,
        "delete_key": C.CERTIFICATES_MANAGE,
    }
    writes = ("upload_header", "delete_header", "upload_key", "delete_key")

    @extend_schema(
        operation_id="manage_certificate_header",
        responses={(200, "image/png"): OpenApiTypes.BINARY},
    )
    def header(self, request: Request, edition_id: int) -> HttpResponse:
        current = certificates.certificate_settings(self.edition)
        if not current.header_storage_name:
            raise Http404
        response = HttpResponse(
            certificates.HEADERS.read(current.header_storage_name), content_type="image/png"
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response

    @extend_schema(
        operation_id="manage_certificate_header_upload",
        request={"multipart/form-data": ImageUploadSerializer},
        responses={200: CertificateSettingsSerializer},
    )
    def upload_header(self, request: Request, edition_id: int) -> Response:
        serializer = ImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data["file"].read(signatures.IMAGE_MAX_BYTES + 1)
        certificates.upload_header(self.edition, data=data, actor=self.actor())
        return self.settings_response()

    @extend_schema(
        operation_id="manage_certificate_header_delete",
        request=None,
        responses={200: CertificateSettingsSerializer},
    )
    def delete_header(self, request: Request, edition_id: int) -> Response:
        certificates.delete_header(self.edition, actor=self.actor())
        return self.settings_response()

    @extend_schema(
        operation_id="manage_certificate_signing_key_upload",
        request={"multipart/form-data": SigningKeyUploadSerializer},
        responses={200: CertificateSettingsSerializer},
    )
    def upload_key(self, request: Request, edition_id: int) -> Response:
        """Certificat PAdES : ouvert avec son mot de passe, puis rechiffré ; le mot de passe
        n'est pas gardé (K19)."""
        serializer = SigningKeyUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data["file"].read(signing.KEY_MAX_BYTES + 1)
        certificates.upload_signing_key(
            self.edition,
            data=data,
            password=serializer.validated_data["password"],
            actor=self.actor(),
        )
        return self.settings_response()

    @extend_schema(
        operation_id="manage_certificate_signing_key_delete",
        request=None,
        responses={200: CertificateSettingsSerializer},
    )
    def delete_key(self, request: Request, edition_id: int) -> Response:
        certificates.delete_signing_key(self.edition, actor=self.actor())
        return self.settings_response()


class DocumentTemplateViewSet(_CertificatesBase):
    """``…/certificates/templates`` : gabarits et signataires désignés, par nature."""

    queryset = DocumentTemplate.objects.none()  # pour le schéma
    serializer_class = DocumentTemplateSerializer
    required_capabilities = {
        "list": C.CERTIFICATES_MANAGE,
        "partial_update": C.CERTIFICATES_MANAGE,
        "signatories": C.CERTIFICATES_MANAGE,
        "preview": C.CERTIFICATES_MANAGE,
    }
    writes = ("partial_update",)

    @extend_schema(
        operation_id="manage_certificate_templates",
        responses={200: DocumentTemplateSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = [
            template_data(certificates.template_for(self.edition, nature))
            for nature in DocumentNature.values
        ]
        return Response(DocumentTemplateSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="manage_certificate_template_update",
        request=DocumentTemplateUpdateSerializer,
        responses={200: DocumentTemplateSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, nature: str) -> Response:
        if nature not in DocumentNature.values:
            raise Http404
        serializer = DocumentTemplateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        view = certificates.update_template(
            self.edition, nature, dict(serializer.validated_data), actor=self.actor()
        )
        return Response(DocumentTemplateSerializer(template_data(view)).data)

    @extend_schema(
        operation_id="manage_certificate_signatories",
        responses={200: SignatorySerializer(many=True)},
    )
    def signatories(self, request: Request, edition_id: int) -> Response:
        """Signatures désignables : complètes, de signataires au rôle actif (K18)."""
        rows = [signatory_data(row) for row in certificates.signatories(self.edition)]
        return Response(SignatorySerializer(rows, many=True).data)

    @extend_schema(
        operation_id="manage_certificate_preview",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def preview(self, request: Request, edition_id: int, nature: str) -> HttpResponse:
        """Aperçu du gabarit sur des données fictives : ni signé, ni stocké."""
        if nature not in DocumentNature.values:
            raise Http404
        content = certificates.preview(self.edition, nature)
        response = pdf_response(content, f"apercu-{nature}.pdf")
        response["Content-Disposition"] = f'inline; filename="apercu-{nature}.pdf"'
        return response


class CertificateViewSet(_CertificatesBase):
    """``…/certificates`` : suivi par nature, émission (file), liste, PDF, révocation."""

    queryset = Certificate.objects.none()
    serializer_class = CertificateSerializer
    required_capabilities = {
        "overview": C.CERTIFICATES_MANAGE,
        "issue": C.CERTIFICATES_MANAGE,
        "list": C.CERTIFICATES_MANAGE,
        "pdf": C.CERTIFICATES_MANAGE,
        "revoke": C.CERTIFICATES_MANAGE,
    }
    writes = ("issue", "revoke")

    def certificate(self, certificate_id: int) -> Certificate:
        found = (
            Certificate.objects.filter(edition=self.edition, pk=certificate_id)
            .select_related("edition")
            .first()
        )
        if found is None:
            raise Http404
        return found

    @extend_schema(
        operation_id="manage_certificates_overview",
        responses={200: CertificateOverviewSerializer(many=True)},
    )
    def overview(self, request: Request, edition_id: int) -> Response:
        rows = certificates.overview(self.edition)
        return Response(CertificateOverviewSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="manage_certificates_issue",
        request=IssueRequestSerializer,
        responses={202: IssueResponseSerializer},
    )
    def issue(self, request: Request, edition_id: int) -> Response:
        """Émission (ou émission complémentaire) d'une nature, confiée à la file : les
        attestations arrivent au passage suivant de ``run_jobs``."""
        serializer = IssueRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = certificates.request_issuance(
            self.edition, serializer.validated_data["nature"], actor=self.actor()
        )
        return Response(IssueResponseSerializer({"job_id": job.pk}).data, status=202)

    @extend_schema(
        operation_id="manage_certificates_list",
        parameters=[
            OpenApiParameter("nature", str, description="Nature."),
            OpenApiParameter("revoked", bool, description="Révoquées seulement."),
            OpenApiParameter("q", str, description="Nom ou référence."),
        ],
        responses={200: CertificateSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        from django.db.models import Q

        rows = Certificate.objects.filter(edition=self.edition).order_by("-issued_at", "-id")
        params = request.query_params
        if params.get("nature"):
            rows = rows.filter(nature=params["nature"])
        if params.get("revoked") in ("1", "true"):
            rows = rows.filter(revoked_at__isnull=False)
        query = params.get("q", "").strip()
        if query:
            rows = rows.filter(Q(name__icontains=query) | Q(details__reference__icontains=query))
        page = self.paginate_queryset(rows)
        data = [certificate_data(row) for row in page]
        return self.get_paginated_response(CertificateSerializer(data, many=True).data)

    @extend_schema(
        operation_id="manage_certificate_pdf",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def pdf(self, request: Request, edition_id: int, certificate_id: int) -> HttpResponse:
        certificate = self.certificate(certificate_id)
        return pdf_response(
            certificates.pdf_bytes(certificate), f"attestation-{certificate.pk}.pdf"
        )

    @extend_schema(
        operation_id="manage_certificate_revoke",
        request=ReasonSerializer,
        responses={200: CertificateSerializer},
    )
    def revoke(self, request: Request, edition_id: int, certificate_id: int) -> Response:
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certificate = certificates.revoke(
            self.certificate(certificate_id),
            reason=serializer.validated_data["reason"],
            actor=self.actor(),
        )
        return Response(CertificateSerializer(certificate_data(certificate)).data)


class MyCertificatesView(APIView):
    """``GET /v1/me/certificates`` : attestations de la personne, toutes éditions."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="me_certificates", responses={200: MyCertificateSerializer(many=True)}
    )
    def get(self, request: Request) -> Response:
        rows = [my_certificate_data(row) for row in certificates.mine(request.user)]
        return Response(MyCertificateSerializer(rows, many=True).data)


class MyCertificatePdfView(APIView):
    """``GET /v1/me/certificates/{id}/pdf`` : PDF d'une attestation valide de la personne."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        operation_id="me_certificate_pdf",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, certificate_id: int) -> HttpResponse:
        found = Certificate.objects.filter(
            user=request.user, pk=certificate_id, revoked_at__isnull=True
        ).first()
        if found is None:
            raise Http404
        return pdf_response(certificates.pdf_bytes(found), f"attestation-{found.pk}.pdf")


class PublicCertificateView(APIView):
    """``GET /v1/public/certificates/{code}`` : vérification publique (K10), limitée en débit ;
    même réponse 404 pour un code inconnu ou mal formé (pas d'énumération)."""

    permission_classes = (AllowAny,)
    authentication_classes = ()
    throttle_scope = "certificate_verify"

    @extend_schema(
        operation_id="public_certificate_verify",
        responses={200: PublicVerificationSerializer},
    )
    def get(self, request: Request, code: str) -> Response:
        data = certificates.verify(code)
        if data is None:
            raise Http404
        response = Response(PublicVerificationSerializer(data).data)
        # « noindex » : posé sur toute l'API par RobotsTagMiddleware.
        response["Cache-Control"] = "no-store"
        return response


# --- Lettres d'invitation (K12) -----------------------------------------------------------------


class _MyLetterBase(APIView):
    permission_classes = (IsAuthenticated,)

    def registration(self, request: Request, registration_id: int) -> Registration:
        found = (
            Registration.objects.filter(user=request.user, pk=registration_id)
            .select_related("edition")
            .first()
        )
        if found is None:
            raise Http404
        return found


class MyLetterView(_MyLetterBase):
    """``GET/POST /v1/registrations/{id}/invitation-letter`` : la demande du participant
    (dernière en date)."""

    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "registration_write"
            return super().get_throttles()
        return []

    @extend_schema(operation_id="registrations_letter", responses={200: MyLetterSerializer})
    def get(self, request: Request, registration_id: int) -> Response:
        letter = letters.current_letter(self.registration(request, registration_id))
        if letter is None:
            raise Http404
        return Response(MyLetterSerializer(my_letter_data(letter)).data)

    @extend_schema(
        operation_id="registrations_letter_request",
        request=LetterRequestSerializer,
        responses={201: MyLetterSerializer},
    )
    def post(self, request: Request, registration_id: int) -> Response:
        serializer = LetterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letter = letters.request_letter(
            self.registration(request, registration_id),
            dict(serializer.validated_data),
            actor=Actor.from_request(request),
        )
        return Response(MyLetterSerializer(my_letter_data(letter)).data, status=201)


class MyLetterPdfView(_MyLetterBase):
    """``GET /v1/registrations/{id}/invitation-letter/pdf`` : la lettre émise."""

    @extend_schema(
        operation_id="registrations_letter_pdf",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, registration_id: int) -> HttpResponse:
        letter = letters.current_letter(self.registration(request, registration_id))
        if letter is None or letter.status != LetterStatus.ISSUED:
            raise Http404
        return pdf_response(letters.pdf_bytes(letter), f"lettre-invitation-{letter.pk}.pdf")


class LetterViewSet(ManageViewSet):
    """``…/invitation-letters`` : demandes et lettres (``letters.manage``) ; émission et
    révocation sous réauthentification récente."""

    queryset = InvitationLetter.objects.none()
    serializer_class = ManageLetterSerializer
    required_capabilities = {
        "list": C.LETTERS_MANAGE,
        "retrieve": C.LETTERS_MANAGE,
        "issue": C.LETTERS_MANAGE,
        "refuse": C.LETTERS_MANAGE,
        "revoke": C.LETTERS_MANAGE,
        "pdf": C.LETTERS_MANAGE,
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action in ("issue", "revoke"):
            permissions.append(RecentAuthRequired())
        return permissions

    def rows(self):
        return InvitationLetter.objects.filter(edition=self.edition).select_related(
            "edition",
            "registration__edition",
            "registration__user__profile",
            "decided_by__profile",
        )

    def letter(self, letter_id: int) -> InvitationLetter:
        found = self.rows().filter(pk=letter_id).first()
        if found is None:
            raise Http404
        return found

    def detail_response(self, letter_id: int) -> Response:
        data = manage_letter_data(self.letter(letter_id), detail=True)
        return Response(ManageLetterDetailSerializer(data).data)

    @extend_schema(
        operation_id="manage_letters_list",
        parameters=[
            OpenApiParameter("status", str, description="Statut."),
            OpenApiParameter("q", str, description="Nom ou référence."),
        ],
        responses={200: ManageLetterSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        from django.db.models import Q

        rows = self.rows().order_by("-created_at", "-id")
        if request.query_params.get("status"):
            rows = rows.filter(status=request.query_params["status"])
        query = request.query_params.get("q", "").strip()
        if query:
            condition = Q(passport_name__icontains=query) | Q(
                registration__user__profile__last_name__icontains=query
            )
            parsed = checkin_services.parse_reference(query)
            if parsed is not None:
                condition |= Q(registration_id=parsed[1])
            rows = rows.filter(condition)
        page = self.paginate_queryset(rows)
        data = [manage_letter_data(row) for row in page]
        return self.get_paginated_response(ManageLetterSerializer(data, many=True).data)

    @extend_schema(
        operation_id="manage_letter_retrieve", responses={200: ManageLetterDetailSerializer}
    )
    def retrieve(self, request: Request, edition_id: int, letter_id: int) -> Response:
        return self.detail_response(letter_id)

    @extend_schema(
        operation_id="manage_letter_issue",
        request=None,
        responses={200: ManageLetterDetailSerializer},
    )
    def issue(self, request: Request, edition_id: int, letter_id: int) -> Response:
        letters.issue_letter(self.letter(letter_id), actor=Actor.from_request(request))
        return self.detail_response(letter_id)

    @extend_schema(
        operation_id="manage_letter_refuse",
        request=ReasonSerializer,
        responses={200: ManageLetterDetailSerializer},
    )
    def refuse(self, request: Request, edition_id: int, letter_id: int) -> Response:
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letters.refuse_letter(
            self.letter(letter_id),
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return self.detail_response(letter_id)

    @extend_schema(
        operation_id="manage_letter_revoke",
        request=ReasonSerializer,
        responses={200: ManageLetterDetailSerializer},
    )
    def revoke(self, request: Request, edition_id: int, letter_id: int) -> Response:
        serializer = ReasonSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        letters.revoke_letter(
            self.letter(letter_id),
            reason=serializer.validated_data["reason"],
            actor=Actor.from_request(request),
        )
        return self.detail_response(letter_id)

    @extend_schema(
        operation_id="manage_letter_pdf",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def pdf(self, request: Request, edition_id: int, letter_id: int) -> HttpResponse:
        letter = self.letter(letter_id)
        if not letter.storage_name:
            raise Http404
        return pdf_response(letters.pdf_bytes(letter), f"lettre-invitation-{letter.pk}.pdf")


# --- Comptoir (K13) ----------------------------------------------------------------------------


class CounterViewSet(ManageViewSet):
    """``POST …/registrations/counter`` : inscription au comptoir, compte créé au besoin."""

    serializer_class = CounterRequestSerializer
    required_capabilities = {"create": C.REGISTRATIONS_MANAGE}

    @extend_schema(
        operation_id="manage_registrations_counter",
        request=CounterRequestSerializer,
        responses={201: CounterResponseSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = CounterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = counter.counter_registration(
            self.edition, dict(serializer.validated_data), actor=Actor.from_request(request)
        )
        if result.account_created:
            # Après validation : le lien de définition du mot de passe part en file.
            counter.send_password_setup(request._request, result.registration.user)
        registration = result.registration
        payload = {
            "registration_id": registration.pk,
            "reference": registration.reference,
            "status": registration.status,
            "total": registration.total,
            "currency": registration.currency,
            "account_created": result.account_created,
        }
        return Response(CounterResponseSerializer(payload).data, status=201)
