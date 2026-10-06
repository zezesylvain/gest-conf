"""Routes des paiements et de la facturation (plan L6 §4).

Gestion : lecture ``finance.read``, mentions de facturation ``pricing.write`` avec
réauthentification récente (J1).
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.html import escape
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.accounts.services.roles import ensure_editable
from apps.core.actor import Actor
from apps.core.permissions import CsrfEnforced
from apps.core.spreadsheet import csv_response
from apps.payments.models import BillingDocument, Payment
from apps.payments.providers import fake
from apps.payments.serializers import (
    BillingDocumentSerializer,
    BillingProfileSerializer,
    FinanceDashboardSerializer,
    IssuedCountSerializer,
    ManualPaymentSerializer,
    PaymentListSerializer,
    RefundSerializer,
)
from apps.payments.services import billing, documents, finance, manual, online
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


def _payments(edition, params):
    rows = (
        Payment.objects.filter(registration__edition=edition)
        .select_related("registration__edition")
        .order_by("-created_at", "-id")
    )
    for name in ("status", "provider", "method"):
        if params.get(name):
            rows = rows.filter(**{name: params[name]})
    return rows


PAYMENT_FILTERS = [
    OpenApiParameter("status", str, description="Statut du paiement."),
    OpenApiParameter("provider", str, description="Fournisseur (manual, fake, cinetpay)."),
    OpenApiParameter("method", str, description="Moyen de paiement."),
]


class PaymentsViewSet(ManageViewSet):
    """``…/billing/payments`` : encaissements de l'édition (``finance.read``), les plus
    récents d'abord ; ``…/billing/payments/export`` : CSV journalisé, réauthentification."""

    serializer_class = PaymentListSerializer
    required_capabilities = {"list": C.FINANCE_READ, "export": C.FINANCE_READ}
    filter_backends = ()

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "export":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(
        operation_id="manage_billing_payments_list",
        parameters=PAYMENT_FILTERS,
        responses={200: PaymentListSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        page = self.paginate_queryset(_payments(self.edition, request.query_params))
        data = [
            {
                "id": row.pk,
                "registration_id": row.registration_id,
                "registration_reference": row.registration.reference,
                "customer": row.registration.billing_name,
                "provider": row.provider,
                "method": row.method,
                "reference": row.reference,
                "provider_reference": row.provider_reference,
                "amount": row.amount,
                "currency": row.currency,
                "status": row.status,
                "provider_status": row.provider_status,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
                "received_on": row.received_on,
                "note": row.note,
            }
            for row in page
        ]
        return self.get_paginated_response(PaymentListSerializer(data, many=True).data)

    @extend_schema(
        operation_id="manage_billing_payments_export",
        parameters=PAYMENT_FILTERS,
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        rows = _payments(self.edition, request.query_params)
        content = finance.export_payments(self.edition, rows, actor=Actor.from_request(request))
        return csv_response(content, f"paiements-{self.edition.code}-{timezone.now():%Y%m%d}.csv")


class DocumentsExportViewSet(ManageViewSet):
    """``…/billing/documents/export`` : pièces de facturation en CSV (export comptable),
    journalisé, réauthentification (J1)."""

    required_capabilities = {"export": C.FINANCE_READ}

    def get_permissions(self):
        return [*super().get_permissions(), RecentAuthRequired()]

    @extend_schema(
        operation_id="manage_billing_documents_export",
        parameters=[OpenApiParameter("kind", str, description="Nature de la pièce.")],
        responses={(200, "text/csv"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        rows = (
            BillingDocument.objects.filter(edition=self.edition)
            .select_related("registration__edition", "original")
            .order_by("kind", "year", "sequence")
        )
        if request.query_params.get("kind"):
            rows = rows.filter(kind=request.query_params["kind"])
        content = finance.export_documents(self.edition, rows, actor=Actor.from_request(request))
        return csv_response(content, f"pieces-{self.edition.code}-{timezone.now():%Y%m%d}.csv")


class FinanceDashboardViewSet(ManageViewSet):
    """``…/billing/dashboard`` : tableau de bord financier (``finance.read``, J12)."""

    serializer_class = FinanceDashboardSerializer
    required_capabilities = {"retrieve": C.FINANCE_READ}

    @extend_schema(operation_id="manage_billing_dashboard")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(FinanceDashboardSerializer(finance.dashboard(self.edition)).data)


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


# --- Paiement en ligne (J6, RG-15) ----------------------------------------------------------------


class PaymentStartSerializer(serializers.Serializer):
    payment_url = serializers.URLField()
    reference = serializers.CharField()


class PaymentCheckSerializer(serializers.Serializer):
    outcome = serializers.CharField()
    status = serializers.CharField()


class MyPaymentView(_MyDocumentsView):
    """``POST /v1/registrations/{id}/pay`` : nouvelle tentative de paiement en ligne ;
    le navigateur est ensuite **dirigé** vers la page hébergée du fournisseur (jamais un
    formulaire : la CSP du portail l'interdirait, bilan de L6.0)."""

    throttle_scope = "registration_write"

    @extend_schema(
        operation_id="registrations_pay", request=None, responses={201: PaymentStartSerializer}
    )
    def post(self, request: Request, registration_id: int) -> Response:
        registration = self.registration(request, registration_id)
        language = "en" if getattr(request, "LANGUAGE_CODE", "fr").startswith("en") else "fr"
        payment, url = online.start_online_payment(
            registration, actor=Actor.from_request(request), language=language
        )
        return Response(
            {"payment_url": url, "reference": payment.reference}, status=status.HTTP_201_CREATED
        )


class MyPaymentCheckView(_MyDocumentsView):
    """``POST /v1/registrations/{id}/payment-check`` : au retour de la page de paiement,
    interroge le fournisseur sur la dernière tentative (le retour lui-même ne prouve rien,
    RG-15)."""

    throttle_scope = "payment_check"

    @extend_schema(
        operation_id="registrations_payment_check",
        request=None,
        responses={200: PaymentCheckSerializer},
    )
    def post(self, request: Request, registration_id: int) -> Response:
        registration = self.registration(request, registration_id)
        outcome = online.check_latest(registration)
        registration.refresh_from_db(fields=["status"])
        return Response({"outcome": outcome, "status": registration.status})


class PaymentWebhookView(APIView):
    """``POST /v1/payments/webhook/{provider}`` : notification du fournisseur (J6).

    Publique, sans session donc sans CSRF, limitée en débit. Le jeton de la notification est
    vérifié, puis le statut **interrogé** : rien n'est cru du corps reçu (RG-15). Réponse
    rapide et sans détail ; ``GET`` répond 200 (contrôle de l'adresse par l'agrégateur)."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "payment_webhook"
    parser_classes = (JSONParser, FormParser, MultiPartParser)

    def _provider(self, provider: str) -> str:
        if provider != settings.GESTCONF_PAYMENT_PROVIDER or provider == "":
            raise Http404
        return provider

    @extend_schema(operation_id="payments_webhook_ping", auth=[], responses={200: None})
    def get(self, request: Request, provider: str) -> Response:
        self._provider(provider)
        return Response({"ok": True})

    @extend_schema(operation_id="payments_webhook", auth=[], request=None, responses={200: None})
    def post(self, request: Request, provider: str) -> Response:
        name = self._provider(provider)
        data = request.data.dict() if hasattr(request.data, "dict") else dict(request.data)
        outcome = online.receive_notification(name, data)
        if outcome == "unreadable":
            return Response({"ok": False}, status=status.HTTP_400_BAD_REQUEST)
        if outcome in ("invalid_token", "unknown_payment"):
            return Response({"ok": False}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"ok": True})


FAKE_PAGE = """<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Paiement de démonstration</title>
<style>body{{font-family:sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem}}
button{{font-size:1rem;padding:.6rem 1.2rem;margin:.4rem .4rem 0 0}}</style></head>
<body><h1>Paiement de démonstration</h1>
<p>Fournisseur factice : aucune somme n'est prélevée.</p>
<p>Référence : <strong>{reference}</strong><br>Montant : <strong>{amount} {currency}</strong></p>
<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{csrf}">
<button name="action" value="pay">Payer</button>
<button name="action" value="fail">Refuser le paiement</button></form></body></html>"""


class FakeCheckoutView(APIView):
    """``/v1/payments/fake/{référence}`` : « page hébergée » du fournisseur factice
    (démonstration, E2E). Absente si le fournisseur configuré n'est pas « fake »."""

    authentication_classes = ()
    permission_classes = (CsrfEnforced,)
    parser_classes = (FormParser, MultiPartParser)

    def _state(self, reference: str) -> dict:
        if settings.GESTCONF_PAYMENT_PROVIDER != "fake":
            raise Http404
        state = fake.get_state(reference)
        if not state:
            raise Http404
        return state

    @extend_schema(exclude=True)
    def get(self, request: Request, reference: str) -> HttpResponse:
        state = self._state(reference)
        page = FAKE_PAGE.format(
            reference=escape(reference),
            amount=escape(state["amount"]),
            currency=escape(state["currency"]),
            csrf=escape(get_token(request._request)),
        )
        return HttpResponse(page, content_type="text/html; charset=utf-8")

    @extend_schema(exclude=True)
    def post(self, request: Request, reference: str) -> HttpResponse:
        state = self._state(reference)
        paid = request.data.get("action") == "pay"
        fake.set_state(reference, status="SUCCESS" if paid else "FAILED")
        online.receive_notification(
            "fake",
            {
                "merchant_transaction_id": reference,
                "transaction_id": state["transaction_id"],
                "notify_token": state["token"],
            },
        )
        return HttpResponseRedirect(state["success_url"] if paid else state["failed_url"])
