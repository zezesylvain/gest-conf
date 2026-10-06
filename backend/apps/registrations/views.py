"""Routes des inscriptions (plan L6 §4).

Gestion (``v1/manage/editions/{id}/registrations/…``) : lecture ``registrations.read``,
paramètres et tarifs ``pricing.write`` (J1). Chaque écriture passe par un service
(journal, verrou, édition archivée en lecture seule).
"""

from __future__ import annotations

from django.db.models import Count, Prefetch
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Profile
from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.registrations.models import (
    Fee,
    PromoCode,
    Registration,
    RegistrationCategory,
    RegistrationOption,
    RegistrationStatus,
)
from apps.registrations.serializers import (
    PERIODS,
    BillingIdentitySerializer,
    CategorySerializer,
    FeeGridSerializer,
    MyRegistrationSerializer,
    OptionSerializer,
    OrderSerializer,
    PromoCodeSerializer,
    ProofUploadSerializer,
    PublicRegistrationSerializer,
    QuoteRequestSerializer,
    QuoteSerializer,
    RegistrationSettingsSerializer,
    registration_data,
)
from apps.registrations.services import orders, pricing
from apps.registrations.services import settings as registration_settings


def local_to_utc_field(data: dict, local_name: str, utc_name: str, timezone: str) -> dict:
    """Échéance saisie à l'heure de l'édition (D13) → instant UTC, erreur sur le champ saisi."""
    from apps.conferences.services import local_to_utc

    if local_name not in data:
        return data
    data = dict(data)
    value = data.pop(local_name)
    try:
        data[utc_name] = None if value is None else local_to_utc(value, timezone)
    except Invalid as exc:
        messages = [message for items in exc.fields.values() for message in items]
        raise Invalid(fields={local_name: messages}) from exc
    return data


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
        data = local_to_utc_field(
            serializer.validated_data,
            "cancellation_deadline_local",
            "cancellation_deadline",
            self.edition.timezone,
        )
        settings = registration_settings.update_registration_settings(
            self.edition, data, actor=Actor.from_request(request)
        )
        return Response(RegistrationSettingsSerializer(settings).data)


# --- Catalogue (J2 à J4) : lecture registrations.read, écriture pricing.write -----------------

CATALOG = {
    "list": C.REGISTRATIONS_READ,
    "create": C.PRICING_WRITE,
    "partial_update": C.PRICING_WRITE,
    "destroy": C.PRICING_WRITE,
    "fees": C.PRICING_WRITE,
}


class _CatalogViewSet(ManageViewSet):
    """Listes courtes, lues en entier et ordonnées par la vue : ni pagination ni tri
    générique (sinon le schéma les décrirait paginées)."""

    pagination_class = None
    filter_backends = ()
    required_capabilities = CATALOG
    model: type

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def item(self, item_id: int):
        found = self.model.objects.filter(pk=item_id, edition=self.edition).first()
        if found is None:
            raise Http404
        return found

    def context(self) -> dict:
        return {"edition": self.edition, "request": self.request}


def _categories(edition):
    return (
        RegistrationCategory.objects.filter(edition=edition)
        .annotate(registration_count=Count("registrations"))
        .prefetch_related("fees")
        .order_by("position", "id")
    )


class CategoryViewSet(_CatalogViewSet):
    """``…/registrations/categories`` : catégories et grilles de tarifs (J2)."""

    serializer_class = CategorySerializer
    model = RegistrationCategory

    def _one(self, category_id: int) -> dict:
        return CategorySerializer(_categories(self.edition).get(pk=category_id)).data

    @extend_schema(operation_id="manage_registration_categories_list")
    def list(self, request: Request, edition_id: int) -> Response:
        return Response(CategorySerializer(_categories(self.edition), many=True).data)

    @extend_schema(operation_id="manage_registration_categories_create")
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = pricing.create_category(
            self.edition, serializer.validated_data, actor=self.actor()
        )
        return Response(self._one(category.pk), status=status.HTTP_201_CREATED)

    @extend_schema(operation_id="manage_registration_categories_update")
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        category = self.item(item_id)
        serializer = CategorySerializer(category, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        pricing.update_category(category, serializer.validated_data, actor=self.actor())
        return Response(self._one(category.pk))

    @extend_schema(operation_id="manage_registration_categories_delete")
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        pricing.delete_category(self.item(item_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_registration_categories_fees",
        request=FeeGridSerializer,
        responses={200: CategorySerializer},
    )
    def fees(self, request: Request, edition_id: int, item_id: int) -> Response:
        category = self.item(item_id)
        serializer = FeeGridSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pricing.set_fees(category, serializer.validated_data["fees"], actor=self.actor())
        return Response(self._one(category.pk))


def _options(edition):
    return (
        RegistrationOption.objects.filter(edition=edition)
        .prefetch_related("categories")
        .order_by("position", "id")
    )


class OptionViewSet(_CatalogViewSet):
    """``…/registrations/options`` : options à quota (J3)."""

    serializer_class = OptionSerializer
    model = RegistrationOption

    @extend_schema(operation_id="manage_registration_options_list")
    def list(self, request: Request, edition_id: int) -> Response:
        return Response(OptionSerializer(_options(self.edition), many=True).data)

    @extend_schema(operation_id="manage_registration_options_create")
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = OptionSerializer(data=request.data, context=self.context())
        serializer.is_valid(raise_exception=True)
        option = pricing.create_option(self.edition, serializer.validated_data, actor=self.actor())
        data = OptionSerializer(_options(self.edition).get(pk=option.pk)).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(operation_id="manage_registration_options_update")
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        option = self.item(item_id)
        serializer = OptionSerializer(
            option, data=request.data, partial=True, context=self.context()
        )
        serializer.is_valid(raise_exception=True)
        pricing.update_option(option, serializer.validated_data, actor=self.actor())
        return Response(OptionSerializer(_options(self.edition).get(pk=option.pk)).data)

    @extend_schema(operation_id="manage_registration_options_delete")
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        pricing.delete_option(self.item(item_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)


def _promo_codes(edition):
    return PromoCode.objects.filter(edition=edition).prefetch_related("categories").order_by("code")


class PromoCodeViewSet(_CatalogViewSet):
    """``…/registrations/promo-codes`` : codes promo (J4)."""

    serializer_class = PromoCodeSerializer
    model = PromoCode

    @extend_schema(operation_id="manage_registration_promo_codes_list")
    def list(self, request: Request, edition_id: int) -> Response:
        return Response(PromoCodeSerializer(_promo_codes(self.edition), many=True).data)

    @extend_schema(operation_id="manage_registration_promo_codes_create")
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = PromoCodeSerializer(data=request.data, context=self.context())
        serializer.is_valid(raise_exception=True)
        data = local_to_utc_field(
            serializer.validated_data, "valid_until_local", "valid_until", self.edition.timezone
        )
        promo = pricing.create_promo_code(self.edition, data, actor=self.actor())
        data = PromoCodeSerializer(_promo_codes(self.edition).get(pk=promo.pk)).data
        return Response(data, status=status.HTTP_201_CREATED)

    @extend_schema(operation_id="manage_registration_promo_codes_update")
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        promo = self.item(item_id)
        serializer = PromoCodeSerializer(
            promo, data=request.data, partial=True, context=self.context()
        )
        serializer.is_valid(raise_exception=True)
        data = local_to_utc_field(
            serializer.validated_data, "valid_until_local", "valid_until", self.edition.timezone
        )
        pricing.update_promo_code(promo, data, actor=self.actor())
        return Response(PromoCodeSerializer(_promo_codes(self.edition).get(pk=promo.pk)).data)

    @extend_schema(operation_id="manage_registration_promo_codes_delete")
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        pricing.delete_promo_code(self.item(item_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Public et participant (J13) ----------------------------------------------------------------


def _current_edition():
    from apps.conferences.services import current_public_edition

    edition = current_public_edition()
    if edition is None:
        raise Http404
    return edition


def public_registration(edition) -> dict:
    settings = registration_settings.registration_settings(edition)
    window = pricing.registration_window(edition)
    categories = (
        RegistrationCategory.objects.filter(edition=edition, is_active=True)
        .prefetch_related(Prefetch("fees", queryset=Fee.objects.all()))
        .order_by("position", "id")
    )
    options = (
        RegistrationOption.objects.filter(edition=edition, is_active=True)
        .prefetch_related("categories")
        .order_by("position", "id")
    )
    return {
        "currency": settings.currency,
        "timezone": edition.timezone,
        "opens_at": window.opens_at,
        "early_bird_end": window.early_bird_end,
        "closes_at": window.closes_at,
        "methods": registration_settings.offered_methods(settings),
        "local_countries": sorted(registration_settings.local_countries(edition, settings)),
        "categories": [
            {
                "code": category.code,
                "label_fr": category.label_fr,
                "label_en": category.label_en,
                "description_fr": category.description_fr,
                "description_en": category.description_en,
                "requires_proof": category.requires_proof,
                "fees": sorted(
                    (
                        {"period": fee.period, "zone": fee.zone, "amount": fee.amount}
                        for fee in category.fees.all()
                    ),
                    key=lambda fee: (PERIODS.index(fee["period"]), fee["zone"]),
                ),
            }
            for category in categories
        ],
        "options": [
            {
                "code": option.code,
                "label_fr": option.label_fr,
                "label_en": option.label_en,
                "description_fr": option.description_fr,
                "description_en": option.description_en,
                "price_local": option.price_local,
                "price_international": option.price_international,
                "limited": option.quota is not None,
                "categories": sorted(category.code for category in option.categories.all()),
            }
            for option in options
        ],
    }


class PublicRegistrationView(APIView):
    """``GET /v1/public/registration`` : catégories, tarifs, options, dates et moyens de
    paiement de l'édition courante (J13), lus au build du portail ; 404 sans édition
    publiée."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="public_registration",
        responses={200: PublicRegistrationSerializer},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        data = PublicRegistrationSerializer(public_registration(_current_edition())).data
        response = Response(data)
        response["Cache-Control"] = "public, max-age=300"
        return response


class QuoteView(APIView):
    """``POST /v1/registrations/quote`` : prix d'une inscription à l'édition courante,
    calculé par le serveur sans engagement (J2 à J4). Zone d'après le pays du profil,
    obligatoire (409 ``profile_incomplete``)."""

    permission_classes = (IsAuthenticated,)
    throttle_scope = "registration_quote"

    @extend_schema(
        operation_id="registration_quote",
        request=QuoteRequestSerializer,
        responses={200: QuoteSerializer},
    )
    def post(self, request: Request) -> Response:
        edition = _current_edition()
        serializer = QuoteRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        country = (
            Profile.objects.filter(user=request.user).values_list("country", flat=True).first()
        )
        if not country:
            raise RuleViolation(
                _("Indiquez votre pays dans votre profil : il détermine le tarif."),
                code=ErrorCode.PROFILE_INCOMPLETE,
                fields={"country": [_("Pays obligatoire.")]},
            )
        if not pricing.is_open_online(edition):
            raise RuleViolation(
                _("Les inscriptions en ligne sont fermées."), code=ErrorCode.REGISTRATION_CLOSED
            )
        quote = pricing.quote(edition, country=country, **serializer.validated_data)
        return Response(
            QuoteSerializer(
                {
                    "category": quote.category.code,
                    "period": quote.period,
                    "zone": quote.zone,
                    "currency": quote.currency,
                    "lines": [line.as_json() for line in quote.lines],
                    "total": quote.total,
                }
            ).data
        )


# --- « Mon inscription » (J13) : le titulaire seul ------------------------------------------------


def my_registration_data(registration: Registration) -> dict:
    data = registration_data(registration)
    settings = registration_settings.registration_settings(registration.edition)
    deadline = settings.cancellation_deadline
    now = timezone.now()
    confirmed_cancellable = (
        registration.status == RegistrationStatus.CONFIRMED
        and deadline is not None
        and now < deadline
    )
    data["can_cancel"] = registration.status == RegistrationStatus.PENDING or confirmed_cancellable
    data["refund_percent"] = settings.refund_percent_before if confirmed_cancellable else None
    data["cancellation_deadline"] = deadline
    return data


def _mine(request: Request):
    return (
        Registration.objects.filter(user=request.user)
        .select_related("edition", "category")
        .prefetch_related("billing_documents", "payments")
    )


class MyRegistrationsView(APIView):
    """``GET /v1/registrations`` : inscriptions du compte, la plus récente d'abord ;
    ``POST`` : commande pour l'édition courante (J5)."""

    permission_classes = (IsAuthenticated,)
    throttle_scope = "registration_write"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(
        operation_id="registrations_list", responses={200: MyRegistrationSerializer(many=True)}
    )
    def get(self, request: Request) -> Response:
        rows = _mine(request).order_by("-created_at", "-id")
        return Response(
            MyRegistrationSerializer([my_registration_data(r) for r in rows], many=True).data
        )

    @extend_schema(
        operation_id="registrations_order",
        request=OrderSerializer,
        responses={201: MyRegistrationSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = OrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        billing = {name: data.pop(name) for name in orders.BILLING_FIELDS if name in data}
        registration = orders.place_order(
            _current_edition(),
            request.user,
            billing=billing,
            actor=Actor.from_request(request),
            **data,
        )
        return Response(
            MyRegistrationSerializer(
                my_registration_data(_mine(request).get(pk=registration.pk))
            ).data,
            status=status.HTTP_201_CREATED,
        )


class _MyRegistrationView(APIView):
    permission_classes = (IsAuthenticated,)

    def registration(self, request: Request, registration_id: int) -> Registration:
        found = _mine(request).filter(pk=registration_id).first()
        if found is None:
            raise Http404
        return found

    def respond(self, request: Request, registration_id: int) -> Response:
        return Response(
            MyRegistrationSerializer(
                my_registration_data(self.registration(request, registration_id))
            ).data
        )


class MyRegistrationView(_MyRegistrationView):
    """``GET /v1/registrations/{id}`` ; ``PATCH`` : identité de facturation (jusqu'à la
    facture)."""

    @extend_schema(operation_id="registrations_retrieve", responses={200: MyRegistrationSerializer})
    def get(self, request: Request, registration_id: int) -> Response:
        return self.respond(request, registration_id)

    @extend_schema(
        operation_id="registrations_billing",
        request=BillingIdentitySerializer,
        responses={200: MyRegistrationSerializer},
    )
    def patch(self, request: Request, registration_id: int) -> Response:
        registration = self.registration(request, registration_id)
        serializer = BillingIdentitySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        orders.update_billing(
            registration, serializer.validated_data, actor=Actor.from_request(request)
        )
        return self.respond(request, registration_id)


class MyRegistrationCancelView(_MyRegistrationView):
    """``POST /v1/registrations/{id}/cancel`` : annulation par le titulaire (J9)."""

    @extend_schema(
        operation_id="registrations_cancel", request=None, responses={200: MyRegistrationSerializer}
    )
    def post(self, request: Request, registration_id: int) -> Response:
        orders.cancel_by_participant(
            self.registration(request, registration_id), actor=Actor.from_request(request)
        )
        return self.respond(request, registration_id)


class MyRegistrationProofView(_MyRegistrationView):
    """``POST /v1/registrations/{id}/proof`` : justificatif (catégorie qui l'exige, J2)."""

    parser_classes = (MultiPartParser,)
    throttle_scope = "registration_upload"

    @extend_schema(
        operation_id="registrations_proof",
        request={"multipart/form-data": ProofUploadSerializer},
        responses={200: MyRegistrationSerializer},
    )
    def post(self, request: Request, registration_id: int) -> Response:
        registration = self.registration(request, registration_id)
        serializer = ProofUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        if upload.size > orders.PROOF_MAX_BYTES:
            raise Invalid(fields={"file": [_("Fichier de 5 Mo au plus.")]})
        orders.upload_proof(
            registration,
            data=upload.read(),
            name=upload.name or "",
            actor=Actor.from_request(request),
        )
        return self.respond(request, registration_id)


class MyRegistrationQrView(_MyRegistrationView):
    """``GET /v1/registrations/{id}/qr`` : QR d'accès (J11), SVG produit par ``segno`` ;
    inscription confirmée seulement. Le jeton n'est jamais dans une URL."""

    @extend_schema(
        operation_id="registrations_qr", responses={(200, "image/svg+xml"): OpenApiTypes.BINARY}
    )
    def get(self, request: Request, registration_id: int) -> HttpResponse:
        registration = self.registration(request, registration_id)
        if not registration.qr_token:
            raise Http404
        return qr_response(registration.qr_token)


def qr_response(token: str) -> HttpResponse:
    import io

    import segno

    buffer = io.BytesIO()
    segno.make(token, error="m", micro=False).save(
        buffer, kind="svg", scale=6, border=4, xmldecl=False
    )
    response = HttpResponse(buffer.getvalue(), content_type="image/svg+xml")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response
