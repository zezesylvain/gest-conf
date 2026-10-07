"""Routes des partenaires (plan L8 §4, N5).

Gestion (``v1/manage/editions/{id}/…``, 2FA) : lues par ``sponsors.read`` (administrateur,
Chair, CO « finances », « communication », « relations extérieures »), écrites par
``sponsors.write`` (administrateur, CO « relations extérieures ») ; export (contacts
compris) sous réauthentification, journalisé.

Public : ``GET /v1/public/sponsors``, partenaires publiés de l'édition courante, lus au build
du portail.
"""

from __future__ import annotations

from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.conferences.services import current_public_edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text, xlsx_bytes, xlsx_response
from apps.sponsors import services
from apps.sponsors.models import Sponsor, SponsorBenefit, SponsorLevel, SponsorStatus
from apps.sponsors.serializers import (
    BenefitUpdateSerializer,
    BenefitWriteSerializer,
    LogoUploadSerializer,
    PublicSponsorsSerializer,
    SponsorDetailSerializer,
    SponsorLevelSerializer,
    SponsorLevelWriteSerializer,
    SponsorsSerializer,
    SponsorWriteSerializer,
)

PUBLIC_CACHE = "public, max-age=300"


class _SponsorsViewSet(ManageViewSet):
    pagination_class = None
    filter_backends = ()

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def sponsors(self):
        return (
            Sponsor.objects.filter(edition=self.edition)
            .select_related("logo", "level")
            .annotate(
                benefits_due=Count("benefits", distinct=True),
                benefits_delivered=Count(
                    "benefits", filter=Q(benefits__delivered_on__isnull=False), distinct=True
                ),
            )
        )

    def sponsor(self, sponsor_id: int) -> Sponsor:
        sponsor = self.sponsors().filter(pk=sponsor_id).first()
        if sponsor is None:
            raise Http404
        return sponsor

    def detail_response(self, sponsor_id: int, code: int = status.HTTP_200_OK) -> Response:
        sponsor = self.sponsors().prefetch_related("benefits").get(pk=sponsor_id)
        return Response(SponsorDetailSerializer(sponsor).data, status=code)


class SponsorViewSet(_SponsorsViewSet):
    """``…/sponsors`` : partenaires, contreparties, export."""

    serializer_class = SponsorDetailSerializer
    required_capabilities = {
        "overview": C.SPONSORS_READ,
        "retrieve": C.SPONSORS_READ,
        "export": C.SPONSORS_READ,
        "create": C.SPONSORS_WRITE,
        "partial_update": C.SPONSORS_WRITE,
        "destroy": C.SPONSORS_WRITE,
        "add_benefit": C.SPONSORS_WRITE,
        "update_benefit": C.SPONSORS_WRITE,
        "remove_benefit": C.SPONSORS_WRITE,
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "export":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(operation_id="manage_sponsors_list", responses={200: SponsorsSerializer})
    def overview(self, request: Request, edition_id: int) -> Response:
        # Action « overview » et non « list » : la réponse est un objet (totaux et partenaires),
        # que le schéma décrirait sinon comme un tableau.
        rows = self.sponsors().order_by("position", "id")
        data = {"totals": services.totals(self.edition), "sponsors": list(rows)}
        return Response(SponsorsSerializer(data).data)

    @extend_schema(
        operation_id="manage_sponsors_create",
        request=SponsorWriteSerializer,
        responses={201: SponsorDetailSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = SponsorWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sponsor = services.create_sponsor(
            self.edition, serializer.validated_data, actor=self.actor()
        )
        return self.detail_response(sponsor.pk, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_sponsors_retrieve", responses={200: SponsorDetailSerializer}
    )
    def retrieve(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        self.sponsor(sponsor_id)
        return self.detail_response(sponsor_id)

    @extend_schema(
        operation_id="manage_sponsors_update",
        request=SponsorWriteSerializer,
        responses={200: SponsorDetailSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        serializer = SponsorWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_sponsor(
            self.sponsor(sponsor_id), serializer.validated_data, actor=self.actor()
        )
        return self.detail_response(sponsor_id)

    @extend_schema(operation_id="manage_sponsors_destroy", responses={204: None})
    def destroy(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        services.delete_sponsor(self.sponsor(sponsor_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_sponsors_benefits_add",
        request=BenefitWriteSerializer,
        responses={201: SponsorDetailSerializer},
    )
    def add_benefit(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        serializer = BenefitWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.add_benefit(
            self.sponsor(sponsor_id), serializer.validated_data["label"], actor=self.actor()
        )
        return self.detail_response(sponsor_id, status.HTTP_201_CREATED)

    def _benefit(self, sponsor_id: int, benefit_id: int) -> SponsorBenefit:
        benefit = (
            SponsorBenefit.objects.filter(
                pk=benefit_id, sponsor_id=sponsor_id, sponsor__edition=self.edition
            )
            .select_related("sponsor__edition")
            .first()
        )
        if benefit is None:
            raise Http404
        return benefit

    @extend_schema(
        operation_id="manage_sponsors_benefits_update",
        request=BenefitUpdateSerializer,
        responses={200: SponsorDetailSerializer},
    )
    def update_benefit(
        self, request: Request, edition_id: int, sponsor_id: int, benefit_id: int
    ) -> Response:
        serializer = BenefitUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.mark_benefit(
            self._benefit(sponsor_id, benefit_id),
            serializer.validated_data["delivered_on"],
            actor=self.actor(),
        )
        return self.detail_response(sponsor_id)

    @extend_schema(
        operation_id="manage_sponsors_benefits_remove",
        request=None,
        responses={200: SponsorDetailSerializer},
    )
    def remove_benefit(
        self, request: Request, edition_id: int, sponsor_id: int, benefit_id: int
    ) -> Response:
        services.remove_benefit(self._benefit(sponsor_id, benefit_id), actor=self.actor())
        return self.detail_response(sponsor_id)

    @extend_schema(
        operation_id="manage_sponsors_export",
        parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int) -> HttpResponse:
        """Export des partenaires, contacts compris (RG-17 : journalisé, réauthentification)."""
        file_format = request.query_params.get("file_format", "csv")
        if file_format not in ("csv", "xlsx"):
            raise Invalid(fields={"file_format": [_("csv ou xlsx attendu.")]})
        header = [
            gettext("Nom"),
            gettext("Niveau"),
            gettext("Statut"),
            gettext("Contribution convenue"),
            gettext("Montant reçu"),
            gettext("Reçu le"),
            gettext("Contact"),
            gettext("Adresse"),
            gettext("Téléphone"),
            gettext("Publié"),
        ]
        rows = [
            [
                sponsor.name,
                sponsor.level.name_fr if sponsor.level else "",
                str(SponsorStatus(sponsor.status).label),
                sponsor.agreed_amount if sponsor.agreed_amount is not None else "",
                sponsor.received_amount if sponsor.received_amount is not None else "",
                sponsor.received_on.isoformat() if sponsor.received_on else "",
                sponsor.contact_name,
                sponsor.contact_email,
                sponsor.contact_phone,
                gettext("oui") if sponsor.published else gettext("non"),
            ]
            for sponsor in self.sponsors().order_by("position", "id")
        ]
        record(
            "sponsor.exported",
            actor=self.actor(),
            edition=self.edition,
            after={"format": file_format, "rows": len(rows)},
        )
        name = f"partenaires-{self.edition.code}-{timezone.now():%Y%m%d}.{file_format}"
        if file_format == "xlsx":
            return xlsx_response(xlsx_bytes(header, rows, title="Partenaires"), name)
        return csv_response(csv_text(header, rows), name)


class SponsorLogoViewSet(_SponsorsViewSet):
    """``…/sponsors/{id}/logo`` : dépôt (multipart) ou retrait du logo."""

    parser_classes = (MultiPartParser,)
    serializer_class = SponsorDetailSerializer
    required_capabilities = {"upload": C.SPONSORS_WRITE, "remove": C.SPONSORS_WRITE}

    @extend_schema(
        operation_id="manage_sponsors_logo_upload",
        request={"multipart/form-data": LogoUploadSerializer},
        responses={200: SponsorDetailSerializer},
    )
    def upload(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        serializer = LogoUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data["file"]
        services.set_logo(
            self.sponsor(sponsor_id),
            data=upload.read(),
            name=upload.name or "",
            actor=self.actor(),
        )
        return self.detail_response(sponsor_id)

    @extend_schema(
        operation_id="manage_sponsors_logo_remove",
        request=None,
        responses={200: SponsorDetailSerializer},
    )
    def remove(self, request: Request, edition_id: int, sponsor_id: int) -> Response:
        services.set_logo(self.sponsor(sponsor_id), data=None, actor=self.actor())
        return self.detail_response(sponsor_id)


class SponsorLevelViewSet(_SponsorsViewSet):
    """``…/sponsor-levels`` : niveaux de partenariat."""

    serializer_class = SponsorLevelSerializer
    required_capabilities = {
        "list": C.SPONSORS_READ,
        "create": C.SPONSORS_WRITE,
        "partial_update": C.SPONSORS_WRITE,
        "destroy": C.SPONSORS_WRITE,
    }

    def levels(self):
        return (
            SponsorLevel.objects.filter(edition=self.edition)
            .annotate(sponsor_count=Count("sponsors"))
            .order_by("position", "id")
        )

    def level(self, level_id: int) -> SponsorLevel:
        level = self.levels().filter(pk=level_id).select_related("edition").first()
        if level is None:
            raise Http404
        return level

    def respond(self, code: int = status.HTTP_200_OK) -> Response:
        return Response(SponsorLevelSerializer(self.levels(), many=True).data, status=code)

    @extend_schema(
        operation_id="manage_sponsor_levels_list",
        responses={200: SponsorLevelSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        return self.respond()

    @extend_schema(
        operation_id="manage_sponsor_levels_create",
        request=SponsorLevelWriteSerializer,
        responses={201: SponsorLevelSerializer(many=True)},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = SponsorLevelWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.create_level(self.edition, serializer.validated_data, actor=self.actor())
        return self.respond(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_sponsor_levels_update",
        request=SponsorLevelWriteSerializer,
        responses={200: SponsorLevelSerializer(many=True)},
    )
    def partial_update(self, request: Request, edition_id: int, level_id: int) -> Response:
        serializer = SponsorLevelWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        services.update_level(self.level(level_id), serializer.validated_data, actor=self.actor())
        return self.respond()

    @extend_schema(
        operation_id="manage_sponsor_levels_destroy",
        request=None,
        responses={200: SponsorLevelSerializer(many=True)},
    )
    def destroy(self, request: Request, edition_id: int, level_id: int) -> Response:
        services.delete_level(self.level(level_id), actor=self.actor())
        return self.respond()


class PublicSponsorsView(APIView):
    """``GET /v1/public/sponsors`` : partenaires publiés de l'édition courante, par niveau
    (N5) ; lu au build du portail (page « Partenaires », pré-rendue)."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="public_sponsors", responses={200: PublicSponsorsSerializer}, auth=[]
    )
    def get(self, request: Request) -> Response:
        edition = current_public_edition()
        if edition is None:
            raise Http404
        response = Response(PublicSponsorsSerializer(services.public_page(edition)).data)
        response["Cache-Control"] = PUBLIC_CACHE
        return response
