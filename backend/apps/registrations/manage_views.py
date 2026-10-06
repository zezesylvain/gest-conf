"""Inscriptions dans la gestion (``v1/manage/editions/{id}/registrations…``, plan L6, J12).

Lecture ``registrations.read`` (CO, Chair, administrateur) ; actions ``registrations.manage``
(CO « finances » et « secrétariat », administrateur) : saisie pour un compte existant,
annulation, gratuité (J1). Paiements manuels, remboursements et pièces : ``apps.payments``.
"""

from __future__ import annotations

from django.db.models import Exists, OuterRef, Q
from django.http import Http404, HttpResponse
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.accounts.services.invitations import display_name
from apps.core.actor import Actor
from apps.core.errors import Invalid
from apps.registrations.models import Registration
from apps.registrations.serializers import (
    CancelSerializer,
    ManageOrderSerializer,
    ManageRegistrationListSerializer,
    ManageRegistrationSerializer,
    WaiverSerializer,
    registration_data,
)
from apps.registrations.services import orders

FILTERS = [
    OpenApiParameter("status", str, description="Statut (en attente, confirmée…)."),
    OpenApiParameter("category", str, description="Code de catégorie."),
    OpenApiParameter("method", str, description="Moyen de paiement."),
    OpenApiParameter("q", str, description="Nom, adresse ou référence."),
]


def person(user: User) -> dict:
    profile = getattr(user, "profile", None)
    return {
        "id": user.pk,
        "name": display_name(user),
        "email": user.email,
        "country": profile.country if profile is not None else "",
    }


def _actor_name(row) -> str:
    return display_name(row.actor) if row.actor_id else row.actor_label


def manage_data(registration: Registration) -> dict:
    data = registration_data(registration)
    data["person"] = person(registration.user)
    data["history"] = [
        {
            "from_status": row.from_status,
            "to_status": row.to_status,
            "at": row.at,
            "actor": _actor_name(row),
            "reason": row.reason,
        }
        for row in registration.history.all()
    ]
    by_pk = {payment.pk: payment for payment in registration.payments.all()}
    for item in data["payments"]:
        payment = by_pk[item["id"]]
        item.update(
            {
                "provider_reference": payment.provider_reference,
                "received_on": payment.received_on,
                "recorded_by": display_name(payment.recorded_by) if payment.recorded_by_id else "",
                "note": payment.note,
            }
        )
    data["refunds"] = [
        {
            "id": refund.pk,
            "amount": refund.amount,
            "method": refund.method,
            "reference": refund.reference,
            "refunded_on": refund.refunded_on,
            "credit_note": refund.credit_note.number if refund.credit_note_id else None,
        }
        for refund in registration.refunds.all()
    ]
    return data


def detailed(edition):
    """Inscriptions de l'édition, avec tout ce que le détail affiche (pas de N+1)."""
    return (
        Registration.objects.filter(edition=edition)
        .select_related("edition", "category", "user__profile")
        .prefetch_related(
            "billing_documents",
            "payments__recorded_by__profile",
            "history__actor__profile",
            "refunds__credit_note",
        )
    )


class _RegistrationsViewSet(ManageViewSet):
    queryset = Registration.objects.all()

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def detailed(self):
        return detailed(self.edition)

    def item(self, item_id: int) -> Registration:
        found = self.detailed().filter(pk=item_id).first()
        if found is None:
            raise Http404
        return found

    def detail_response(self, item_id: int, code: int = status.HTTP_200_OK) -> Response:
        return Response(
            ManageRegistrationSerializer(manage_data(self.item(item_id))).data, status=code
        )


class RegistrationListViewSet(_RegistrationsViewSet):
    """``…/registrations`` : liste filtrable et paginée ; saisie par le CO pour un compte
    existant (après la clôture : tarif « sur place »)."""

    serializer_class = ManageRegistrationListSerializer
    required_capabilities = {"list": C.REGISTRATIONS_READ, "create": C.REGISTRATIONS_MANAGE}
    filter_backends = ()

    def filtered(self):
        from apps.payments.models import BillingDocument, DocumentKind

        params = self.request.query_params
        rows = (
            Registration.objects.filter(edition=self.edition)
            .select_related("edition", "category", "user__profile")
            .annotate(
                invoiced=Exists(
                    BillingDocument.objects.filter(
                        registration=OuterRef("pk"), kind=DocumentKind.INVOICE
                    )
                )
            )
            .order_by("-created_at", "-id")
        )
        if params.get("status"):
            rows = rows.filter(status=params["status"])
        if params.get("category"):
            rows = rows.filter(category__code=params["category"])
        if params.get("method"):
            rows = rows.filter(method=params["method"])
        query = params.get("q", "").strip()
        if query:
            condition = (
                Q(user__email__icontains=query)
                | Q(user__profile__last_name__icontains=query)
                | Q(user__profile__first_name__icontains=query)
                | Q(billing_name__icontains=query)
            )
            reference = query.upper().rsplit("-I", 1)
            if len(reference) == 2 and reference[1].isdigit():
                condition |= Q(pk=int(reference[1]))
            rows = rows.filter(condition)
        return rows

    @extend_schema(
        operation_id="manage_registrations_list",
        parameters=FILTERS,
        responses={200: ManageRegistrationListSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        page = self.paginate_queryset(self.filtered())
        rows = [
            {
                "id": row.pk,
                "reference": row.reference,
                "person": person(row.user),
                "category": {
                    "code": row.category.code,
                    "label_fr": row.category.label_fr,
                    "label_en": row.category.label_en,
                    "requires_proof": row.category.requires_proof,
                },
                "status": row.status,
                "method": row.method,
                "total": row.total,
                "currency": row.currency,
                "due_at": row.due_at,
                "created_at": row.created_at,
                "confirmed_at": row.confirmed_at,
                "has_proof": bool(row.proof_storage_name),
                "has_invoice": row.invoiced,
            }
            for row in page
        ]
        return self.get_paginated_response(ManageRegistrationListSerializer(rows, many=True).data)

    @extend_schema(
        operation_id="manage_registrations_create",
        request=ManageOrderSerializer,
        responses={201: ManageRegistrationSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = ManageOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        email = data.pop("email")
        user = User.objects.filter(
            email__iexact=email, is_active=True, anonymized_at__isnull=True
        ).first()
        if user is None:
            raise Invalid(fields={"email": [_("Aucun compte actif avec cette adresse.")]})
        billing = {name: data.pop(name) for name in orders.BILLING_FIELDS if name in data}
        registration = orders.place_order(
            self.edition,
            user,
            billing=billing,
            actor=self.actor(),
            by_committee=True,
            **data,
        )
        return self.detail_response(registration.pk, status.HTTP_201_CREATED)


class RegistrationDetailViewSet(_RegistrationsViewSet):
    """``…/registrations/{id}`` : détail ; ``…/cancel``, ``…/waive`` : actions du CO."""

    serializer_class = ManageRegistrationSerializer
    required_capabilities = {
        "retrieve": C.REGISTRATIONS_READ,
        "cancel": C.REGISTRATIONS_MANAGE,
        "waive": C.REGISTRATIONS_MANAGE,
        "proof": C.REGISTRATIONS_READ,
    }

    @extend_schema(operation_id="manage_registrations_retrieve")
    def retrieve(self, request: Request, edition_id: int, item_id: int) -> Response:
        return self.detail_response(item_id)

    @extend_schema(
        operation_id="manage_registrations_cancel",
        request=CancelSerializer,
        responses={200: ManageRegistrationSerializer},
    )
    def cancel(self, request: Request, edition_id: int, item_id: int) -> Response:
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orders.cancel_by_committee(
            self.item(item_id),
            reason=serializer.validated_data["reason"],
            percent=serializer.validated_data.get("refund_percent"),
            actor=self.actor(),
        )
        return self.detail_response(item_id)

    @extend_schema(
        operation_id="manage_registrations_waive",
        request=WaiverSerializer,
        responses={200: ManageRegistrationSerializer},
    )
    def waive(self, request: Request, edition_id: int, item_id: int) -> Response:
        serializer = WaiverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        orders.grant_waiver(
            self.item(item_id), reason=serializer.validated_data["reason"], actor=self.actor()
        )
        return self.detail_response(item_id)

    @extend_schema(
        operation_id="manage_registrations_proof",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def proof(self, request: Request, edition_id: int, item_id: int) -> HttpResponse:
        """Justificatif déposé (règle n° 8 : endpoint authentifié, type vérifié au dépôt)."""
        registration = self.item(item_id)
        if not registration.proof_storage_name:
            raise Http404
        try:
            data = orders.PROOFS.read(registration.proof_storage_name)
        except FileNotFoundError as error:
            raise Http404 from error
        kinds = {"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png"}
        response = HttpResponse(data, content_type=kinds[registration.proof_kind])
        extension = "jpg" if registration.proof_kind == "jpeg" else registration.proof_kind
        response["Content-Disposition"] = (
            f'attachment; filename="justificatif-{registration.reference}.{extension}"'
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
