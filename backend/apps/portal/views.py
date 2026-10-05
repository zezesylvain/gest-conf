"""API du CMS du portail (plan L2 §4).

Gestion : ``v1/manage/editions/{id}/portal/…`` (``ManageViewSet`` : 401 → 404 → 403, 2FA ;
lecture ``edition.read``, écriture ``portal.write``). Public : ``v1/public/portal/…``
(anonyme, liste blanche du test de plateforme), édition courante publiée seulement.
Aucune pagination (``pagination_class = None``) : listes courtes, lues en entier.
"""

from __future__ import annotations

from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability
from apps.conferences.serializers import PublicEditionSerializer
from apps.conferences.services import current_public_edition
from apps.core.actor import Actor
from apps.portal import services
from apps.portal.models import MenuItem, MenuLocation, Page, PageSection, Section
from apps.portal.serializers import (
    MenuItemSerializer,
    MenuOrderSerializer,
    PageSerializer,
    PreviewSerializer,
    PublicationStatusSerializer,
    PublicCompositionSerializer,
    PublicMenuItemSerializer,
    PublicRoutesSerializer,
    PublicSiteSerializer,
    SectionOrderSerializer,
    SectionRefSerializer,
    SectionSerializer,
    SectionWriteSerializer,
)

C = Capability
READ, WRITE = C.EDITION_READ, C.PORTAL_WRITE
PUBLIC_CACHE = "public, max-age=300"


def _actor(request: Request) -> Actor:
    return Actor.from_request(request)


class _PortalViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, ManageViewSet):
    pagination_class = None
    lookup_url_kwarg = "item_id"
    required_capabilities = {
        "list": READ,
        "retrieve": READ,
        "create": WRITE,
        "partial_update": WRITE,
        "destroy": WRITE,
    }


# --- Gestion : sections -----------------------------------------------------------------------


class SectionViewSet(_PortalViewSet):
    serializer_class = SectionSerializer
    queryset = Section.objects.prefetch_related(
        Prefetch("placements", queryset=PageSection.objects.select_related("page"))
    ).order_by("code", "id")
    required_capabilities = {**_PortalViewSet.required_capabilities, "preview": WRITE}

    def _reread(self, section: Section) -> dict:
        return SectionSerializer(self.get_queryset().get(pk=section.pk)).data

    @extend_schema(request=SectionWriteSerializer, responses={201: SectionSerializer})
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = SectionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        section = services.create_section(
            self.edition, serializer.validated_data, actor=_actor(request)
        )
        return Response(self._reread(section), status=status.HTTP_201_CREATED)

    @extend_schema(request=SectionWriteSerializer, responses={200: SectionSerializer})
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        serializer = SectionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        section = services.update_section(
            self.get_object(), serializer.validated_data, actor=_actor(request)
        )
        return Response(self._reread(section))

    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        services.delete_section(self.get_object(), actor=_actor(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_portal_sections_preview",
        request=PreviewSerializer,
        responses={200: PreviewSerializer},
    )
    @action(detail=False, methods=["post"])
    def preview(self, request: Request, edition_id: int) -> Response:
        """Aperçu du HTML tel qu'il sera enregistré (assaini), sans rien écrire."""
        serializer = PreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                language: services.preview_html(self.edition, serializer.validated_data[language])
                for language in ("body_fr", "body_en")
            }
        )


# --- Gestion : pages et composition -------------------------------------------------------------


class PageViewSet(_PortalViewSet):
    serializer_class = PageSerializer
    queryset = Page.objects.prefetch_related(
        Prefetch("placements", queryset=PageSection.objects.select_related("section"))
    ).order_by("-is_system", "slug", "id")
    required_capabilities = {
        **_PortalViewSet.required_capabilities,
        "attach": WRITE,
        "detach": WRITE,
        "reorder": WRITE,
    }

    def _reread(self, page: Page) -> dict:
        return PageSerializer(self.get_queryset().get(pk=page.pk)).data

    def _section(self, section_id: int) -> Section:
        return get_object_or_404(Section, pk=section_id, edition=self.edition)

    def create(self, request: Request, edition_id: int) -> Response:
        serializer = PageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = services.create_page(self.edition, serializer.validated_data, actor=_actor(request))
        return Response(self._reread(page), status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        page = self.get_object()
        serializer = PageSerializer(page, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        page = services.update_page(page, serializer.validated_data, actor=_actor(request))
        return Response(self._reread(page))

    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        services.delete_page(self.get_object(), actor=_actor(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_portal_pages_attach",
        request=SectionRefSerializer,
        responses={200: PageSerializer},
    )
    @action(detail=True, methods=["post"])
    def attach(self, request: Request, edition_id: int, item_id: int) -> Response:
        """Pose une section (à la fin, ou à ``position``) ; composition relue."""
        serializer = SectionRefSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = self.get_object()
        services.attach_section(
            page,
            self._section(serializer.validated_data["section"]),
            position=serializer.validated_data.get("position"),
            actor=_actor(request),
        )
        return Response(self._reread(page))

    @extend_schema(
        operation_id="manage_portal_pages_detach",
        request=SectionRefSerializer,
        responses={200: PageSerializer},
    )
    @action(detail=True, methods=["post"])
    def detach(self, request: Request, edition_id: int, item_id: int) -> Response:
        serializer = SectionRefSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = self.get_object()
        services.detach_section(
            page, self._section(serializer.validated_data["section"]), actor=_actor(request)
        )
        return Response(self._reread(page))

    @extend_schema(
        operation_id="manage_portal_pages_reorder",
        request=SectionOrderSerializer,
        responses={200: PageSerializer},
    )
    @action(detail=True, methods=["post"])
    def reorder(self, request: Request, edition_id: int, item_id: int) -> Response:
        """Ordre en liste complète des sections posées, sinon 400."""
        serializer = SectionOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        page = self.get_object()
        services.reorder_sections(
            page, serializer.validated_data["sections"], actor=_actor(request)
        )
        return Response(self._reread(page))


# --- Gestion : menus -------------------------------------------------------------------------


class MenuItemViewSet(_PortalViewSet):
    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.select_related("page").order_by("location", "position", "id")
    required_capabilities = {**_PortalViewSet.required_capabilities, "reorder": WRITE}

    def get_queryset(self):
        queryset = super().get_queryset()
        location = self.request.query_params.get("location")
        return queryset.filter(location=location) if location else queryset

    @extend_schema(
        parameters=[
            OpenApiParameter("location", enum=MenuLocation.values, required=False, type=str)
        ]
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    def create(self, request: Request, edition_id: int) -> Response:
        serializer = MenuItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = services.create_menu_item(
            self.edition, serializer.validated_data, actor=_actor(request)
        )
        return Response(MenuItemSerializer(item).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        item = self.get_object()
        serializer = MenuItemSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = services.update_menu_item(item, serializer.validated_data, actor=_actor(request))
        return Response(MenuItemSerializer(item).data)

    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        services.delete_menu_item(self.get_object(), actor=_actor(request))
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_portal_menu_reorder",
        request=MenuOrderSerializer,
        responses={200: MenuItemSerializer(many=True)},
    )
    @action(detail=False, methods=["post"])
    def reorder(self, request: Request, edition_id: int) -> Response:
        serializer = MenuOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = services.reorder_menu(
            self.edition,
            serializer.validated_data["location"],
            serializer.validated_data["items"],
            actor=_actor(request),
        )
        return Response(MenuItemSerializer(items, many=True).data)


class PublicationStatusViewSet(ManageViewSet):
    """``GET …/portal/status`` : dernière mise en ligne, modifications non publiées (E1)."""

    serializer_class = PublicationStatusSerializer
    required_capabilities = {"retrieve": READ}

    @extend_schema(operation_id="manage_portal_status")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(PublicationStatusSerializer(services.publication_status(self.edition)).data)


# --- Public ----------------------------------------------------------------------------------


class _PublicPortalView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def edition(self):
        edition = current_public_edition()
        if edition is None:
            raise Http404
        return edition

    def respond(self, data) -> Response:
        response = Response(data)
        response["Cache-Control"] = PUBLIC_CACHE
        return response


def _site_data(edition) -> dict:
    """Données des gabarits et des sections « données » : une seule lecture de l'édition.
    Documents : L2.4 ; comités (avec consentements) : L2.6."""
    return {
        "edition": PublicEditionSerializer(edition).data,
        "documents": [],
        "committees": {"scientific": [], "organizing": []},
    }


class PublicRoutesView(_PublicPortalView):
    """Routes à pré-rendre et leur **nombre attendu** (vérifié au build, plan L2 §2.2)."""

    @extend_schema(
        operation_id="public_portal_routes", responses={200: PublicRoutesSerializer}, auth=[]
    )
    def get(self, request: Request) -> Response:
        edition = self.edition()
        routes = services.public_routes(edition)
        return self.respond(
            PublicRoutesSerializer(
                {"routes": routes, "expected": len(routes), "pages": services.public_pages(edition)}
            ).data
        )


class PublicCompositionView(_PublicPortalView):
    """Page publiée et ses sections publiées, dans l'ordre ; 404 si inconnue (le gabarit
    d'une page du site s'affiche alors seul)."""

    @extend_schema(
        operation_id="public_portal_page", responses={200: PublicCompositionSerializer}, auth=[]
    )
    def get(self, request: Request, slug: str) -> Response:
        edition = self.edition()
        page = get_object_or_404(
            services.public_pages(edition).prefetch_related(
                services.published_placements_prefetch()
            ),
            slug=slug,
        )
        sections = [placement.section for placement in page.published_placements]
        context = {"site": _site_data(edition) if any(s.is_data for s in sections) else None}
        return self.respond(
            PublicCompositionSerializer({"page": page, "sections": sections}, context=context).data
        )


class PublicMenuView(_PublicPortalView):
    """Entrées publiées d'un menu ; une entrée vers une page non publiée est omise."""

    @extend_schema(
        operation_id="public_portal_menu",
        parameters=[
            OpenApiParameter("location", enum=MenuLocation.values, required=True, type=str)
        ],
        responses={200: PublicMenuItemSerializer(many=True)},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        edition = self.edition()
        location = request.query_params.get("location")
        if location not in MenuLocation.values:
            raise Http404
        items = (
            MenuItem.objects.filter(edition=edition, location=location, published=True)
            .select_related("page")
            .order_by("position", "id")
        )
        data = []
        for item in items:
            if item.page is not None:
                if not (item.page.is_system or item.page.published):
                    continue
                href_fr, href_en = item.page.paths["fr"], item.page.paths["en"]
            else:
                href_fr = href_en = item.url
            data.append(
                {
                    "label_fr": item.label_fr,
                    "label_en": item.label_en,
                    "href_fr": href_fr,
                    "href_en": href_en,
                    "new_tab": item.new_tab,
                    "page": item.page.slug if item.page else None,
                }
            )
        return self.respond(PublicMenuItemSerializer(data, many=True).data)


class PublicSiteView(_PublicPortalView):
    """Données des gabarits des pages du site, en un appel."""

    @extend_schema(
        operation_id="public_portal_site", responses={200: PublicSiteSerializer}, auth=[]
    )
    def get(self, request: Request) -> Response:
        return self.respond(_site_data(self.edition()))
