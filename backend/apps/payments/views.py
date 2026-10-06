"""Routes des paiements et de la facturation (plan L6 §4).

Gestion : lecture ``finance.read``, mentions de facturation ``pricing.write`` avec
réauthentification récente (J1).
"""

from __future__ import annotations

import hashlib

from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.accounts.services.roles import ensure_editable
from apps.core.actor import Actor
from apps.payments.models import BillingDocument
from apps.payments.serializers import (
    BillingDocumentSerializer,
    BillingProfileSerializer,
    IssuedCountSerializer,
    ManualPaymentSerializer,
    RefundSerializer,
)
from apps.payments.services import billing, documents, manual
from apps.registrations.manage_views import detailed, manage_data
from apps.registrations.models import Registration
from apps.registrations.serializers import DocumentRefSerializer, ManageRegistrationSerializer


class BillingProfileViewSet(ManageViewSet):
    """``…/billing/profile`` : mentions de facturation de l'édition (Q8)."""

    serializer_class = BillingProfileSerializer
    required_capabilities = {"retrieve": C.FINANCE_READ, "partial_update": C.PRICING_WRITE}

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "partial_update":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(operation_id="manage_billing_profile_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(BillingProfileSerializer(billing.billing_profile(self.edition)).data)

    @extend_schema(operation_id="manage_billing_profile_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        current = billing.billing_profile(self.edition)
        serializer = BillingProfileSerializer(current, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = billing.update_billing_profile(
            self.edition, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(BillingProfileSerializer(profile).data)


# --- Pièces et paiements d'une inscription (J7 à J9) ---------------------------------------------


def pdf_response(document: BillingDocument) -> HttpResponse:
    """PDF d'une pièce (règle n° 8 : endpoint authentifié), empreinte contrôlée à la lecture."""
    try:
        data = documents.read_document(document)
    except FileNotFoundError as error:
        raise Http404 from error
    if hashlib.sha256(data).hexdigest() != document.sha256:
        raise Http404
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{document.number}.pdf"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


class _RegistrationActionViewSet(ManageViewSet):
    """Actions financières sur une inscription de l'édition (404 sinon)."""

    def registration(self, item_id: int) -> Registration:
        found = (
            Registration.objects.filter(pk=item_id, edition=self.edition)
            .select_related("edition", "user")
            .first()
        )
        if found is None:
            raise Http404
        return found

    def detail_response(self, item_id: int, code: int = status.HTTP_200_OK) -> Response:
        registration = detailed(self.edition).get(pk=item_id)
        return Response(ManageRegistrationSerializer(manage_data(registration)).data, status=code)


class ManualPaymentViewSet(_RegistrationActionViewSet):
    """``…/registrations/{id}/payments`` : paiement reçu hors ligne, validé par le CO avec
    réauthentification (J1, J7) ; confirme l'inscription et émet la facture."""

    serializer_class = ManualPaymentSerializer
    required_capabilities = {"create": C.REGISTRATIONS_MANAGE}

    def get_permissions(self):
        return [*super().get_permissions(), RecentAuthRequired()]

    @extend_schema(
        operation_id="manage_registrations_payment",
        request=ManualPaymentSerializer,
        responses={201: ManageRegistrationSerializer},
    )
    def create(self, request: Request, edition_id: int, item_id: int) -> Response:
        registration = self.registration(item_id)
        serializer = ManualPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documents.prepare_series(self.edition)
        manual.record_manual_payment(
            registration, actor=Actor.from_request(request), **serializer.validated_data
        )
        return self.detail_response(item_id, status.HTTP_201_CREATED)


class RefundViewSet(_RegistrationActionViewSet):
    """``…/registrations/{id}/refunds`` : remboursement fait hors plateforme, avoir émis
    (J9), avec réauthentification (J1)."""

    serializer_class = RefundSerializer
    required_capabilities = {"create": C.REGISTRATIONS_MANAGE}

    def get_permissions(self):
        return [*super().get_permissions(), RecentAuthRequired()]

    @extend_schema(
        operation_id="manage_registrations_refund",
        request=RefundSerializer,
        responses={201: ManageRegistrationSerializer},
    )
    def create(self, request: Request, edition_id: int, item_id: int) -> Response:
        registration = self.registration(item_id)
        serializer = RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        documents.prepare_series(self.edition)
        manual.record_refund(
            registration, actor=Actor.from_request(request), **serializer.validated_data
        )
        return self.detail_response(item_id, status.HTTP_201_CREATED)


class ProformaViewSet(_RegistrationActionViewSet):
    """``…/registrations/{id}/proforma`` : nouvelle pro forma (bon de commande, J7)."""

    serializer_class = ManageRegistrationSerializer
    required_capabilities = {"create": C.REGISTRATIONS_MANAGE}

    @extend_schema(
        operation_id="manage_registrations_proforma",
        request=None,
        responses={201: ManageRegistrationSerializer},
    )
    def create(self, request: Request, edition_id: int, item_id: int) -> Response:
        registration = self.registration(item_id)
        documents.prepare_series(self.edition)
        documents.issue_proforma(registration, actor=Actor.from_request(request))
        return self.detail_response(item_id, status.HTTP_201_CREATED)


class RegistrationDocumentViewSet(_RegistrationActionViewSet):
    """``…/registrations/{id}/documents/{doc}`` : PDF d'une pièce de l'inscription."""

    required_capabilities = {"retrieve": C.REGISTRATIONS_READ}

    @extend_schema(
        operation_id="manage_registrations_document",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def retrieve(
        self, request: Request, edition_id: int, item_id: int, document_id: int
    ) -> HttpResponse:
        document = BillingDocument.objects.filter(
            pk=document_id, registration=self.registration(item_id)
        ).first()
        if document is None:
            raise Http404
        return pdf_response(document)


class BillingDocumentsViewSet(ManageViewSet):
    """``…/billing/documents`` : factures, avoirs et pro forma de l'édition (``finance.read``),
    les plus récentes d'abord ; filtre ``kind``."""

    serializer_class = BillingDocumentSerializer
    required_capabilities = {"list": C.FINANCE_READ}
    filter_backends = ()

    @extend_schema(
        operation_id="manage_billing_documents_list",
        parameters=[OpenApiParameter("kind", str, description="Nature de la pièce.")],
        responses={200: BillingDocumentSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = (
            BillingDocument.objects.filter(edition=self.edition)
            .select_related("registration__edition", "original")
            .order_by("-issued_at", "-id")
        )
        kind = request.query_params.get("kind")
        if kind:
            rows = rows.filter(kind=kind)
        page = self.paginate_queryset(rows)
        data = [
            {
                "id": row.pk,
                "kind": row.kind,
                "number": row.number,
                "registration_id": row.registration_id,
                "registration_reference": row.registration.reference,
                "customer": row.customer.get("name", ""),
                "original": row.original.number if row.original_id else None,
                "amount": row.amount,
                "currency": row.currency,
                "issued_at": row.issued_at,
            }
            for row in page
        ]
        return self.get_paginated_response(BillingDocumentSerializer(data, many=True).data)


class IssuePendingInvoicesViewSet(ManageViewSet):
    """``…/billing/documents/issue-pending`` : factures des paiements reçus avant que les
    mentions de facturation soient complètes (J8), avec réauthentification."""

    serializer_class = IssuedCountSerializer
    required_capabilities = {"create": C.REGISTRATIONS_MANAGE}

    def get_permissions(self):
        return [*super().get_permissions(), RecentAuthRequired()]

    @extend_schema(
        operation_id="manage_billing_issue_pending",
        request=None,
        responses={200: IssuedCountSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        ensure_editable(self.edition)
        issued = documents.issue_pending_invoices(self.edition, actor=Actor.from_request(request))
        return Response({"issued": issued})


# --- Participant : ses pièces et sa pro forma ---------------------------------------------------


class _MyDocumentsView(APIView):
    permission_classes = (IsAuthenticated,)

    def registration(self, request: Request, registration_id: int) -> Registration:
        found = (
            Registration.objects.filter(pk=registration_id, user=request.user)
            .select_related("edition", "user")
            .first()
        )
        if found is None:
            raise Http404
        return found


class MyDocumentView(_MyDocumentsView):
    """``GET /v1/registrations/{id}/documents/{doc}`` : PDF d'une pièce, au titulaire seul."""

    @extend_schema(
        operation_id="registrations_document",
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    def get(self, request: Request, registration_id: int, document_id: int) -> HttpResponse:
        registration = self.registration(request, registration_id)
        document = BillingDocument.objects.filter(pk=document_id, registration=registration).first()
        if document is None:
            raise Http404
        return pdf_response(document)


class MyProformaView(_MyDocumentsView):
    """``POST /v1/registrations/{id}/proforma`` : nouvelle pro forma (après un changement
    d'identité de facturation, par exemple), inscription en attente seulement."""

    throttle_scope = "registration_write"

    @extend_schema(
        operation_id="registrations_proforma",
        request=None,
        responses={201: DocumentRefSerializer},
    )
    def post(self, request: Request, registration_id: int) -> Response:
        registration = self.registration(request, registration_id)
        documents.prepare_series(registration.edition)
        document = documents.issue_proforma(registration, actor=Actor.from_request(request))
        return Response(
            DocumentRefSerializer(
                {
                    "id": document.pk,
                    "kind": document.kind,
                    "number": document.number,
                    "amount": document.amount,
                    "currency": document.currency,
                    "issued_at": document.issued_at,
                }
            ).data,
            status=status.HTTP_201_CREATED,
        )
