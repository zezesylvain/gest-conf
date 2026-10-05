"""API du CMS du portail (plan L2 §4).

Gestion : ``v1/manage/editions/{id}/portal/…`` (``ManageViewSet`` : 401 → 404 → 403, 2FA ;
lecture ``edition.read``, écriture ``portal.write``). Public : ``v1/public/portal/…``
(anonyme, liste blanche du test de plateforme), édition courante publiée seulement.
Aucune pagination (``pagination_class = None``) : listes courtes, lues en entier.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Prefetch
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability
from apps.conferences.serializers import PublicEditionSerializer
from apps.conferences.services import current_public_edition
from apps.core import public_files
from apps.core.actor import Actor
from apps.core.models import PublicFile, PublicFileKind
from apps.portal import services
from apps.portal.models import MenuItem, MenuLocation, Page, PageSection, Section
from apps.portal.serializers import (
    FileUploadSerializer,
    MenuItemSerializer,
    MenuOrderSerializer,
    PageSerializer,
    PosterSerializer,
    PreviewSerializer,
    PublicationStatusSerializer,
    PublicCompositionSerializer,
    PublicFileRefSerializer,
    PublicFileSerializer,
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
    queryset = (
        Section.objects.select_related("image")
        .prefetch_related(
            Prefetch("placements", queryset=PageSection.objects.select_related("page"))
        )
        .order_by("code", "id")
    )
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


# --- Gestion : fichiers publics (L2.4) ------------------------------------------------------


class PublicFileViewSet(_PortalViewSet):
    """Documents et images de l'édition : téléversement (multipart), titres, ordre,
    publication ; suppression refusée tant que le fichier est utilisé (409 ``in_use``)."""

    serializer_class = PublicFileSerializer
    queryset = PublicFile.objects.filter(kind__in=services.PORTAL_FILE_KINDS).order_by(
        "kind", "position", "id"
    )
    parser_classes = (JSONParser, MultiPartParser)

    required_capabilities = {**_PortalViewSet.required_capabilities, "content": READ}

    def get_throttles(self):
        if self.action == "create":
            self.throttle_scope = "portal_upload"
        return super().get_throttles()

    @extend_schema(
        operation_id="manage_portal_files_content",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def content(self, request: Request, edition_id: int, item_id: int) -> HttpResponse:
        """Aperçu dans la gestion, publié ou non (la lecture de l'édition suffit)."""
        public_file = self.get_object()
        try:
            data = public_files.read(public_file)
        except FileNotFoundError as exc:
            raise Http404 from exc
        response = HttpResponse(data, content_type=public_file.content_type)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        disposition = "inline" if public_file.kind != PublicFileKind.DOCUMENT else "attachment"
        name = public_files.safe_download_name(public_file.original_name, public_file.extension)
        response["Content-Disposition"] = f'{disposition}; filename="{name}"'
        return response

    def get_queryset(self):
        queryset = super().get_queryset()
        kind = self.request.query_params.get("kind")
        return queryset.filter(kind=kind) if kind else queryset

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "kind", enum=list(services.PORTAL_FILE_KINDS), required=False, type=str
            )
        ]
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        request={"multipart/form-data": FileUploadSerializer},
        responses={201: PublicFileSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stored = services.upload_file(
            self.edition,
            data=data["file"].read(),
            name=data["file"].name,
            kind=data["kind"],
            title_fr=data["title_fr"],
            title_en=data["title_en"],
            actor=_actor(request),
        )
        return Response(PublicFileSerializer(stored).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        public_file = self.get_object()
        serializer = PublicFileSerializer(public_file, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        public_file = services.update_file(
            public_file, serializer.validated_data, actor=_actor(request)
        )
        return Response(PublicFileSerializer(public_file).data)

    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        services.delete_file(self.get_object(), actor=_actor(request))
        return Response(status=status.HTTP_204_NO_CONTENT)


class PosterViewSet(ManageViewSet):
    """``…/portal/poster`` : affiche de l'édition (image Open Graph, E7)."""

    serializer_class = PosterSerializer
    required_capabilities = {"retrieve": READ, "update": WRITE}

    def _payload(self, edition) -> dict:
        poster = edition.poster if edition.poster_id else None
        return {"file": edition.poster_id, "poster": poster}

    @extend_schema(operation_id="manage_portal_poster")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(PosterSerializer(self._payload(self.edition)).data)

    @extend_schema(operation_id="manage_portal_poster_update", request=PosterSerializer)
    def update(self, request: Request, edition_id: int) -> Response:
        serializer = PosterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_id = serializer.validated_data["file"]
        poster = (
            get_object_or_404(PublicFile, pk=file_id, edition=self.edition)
            if file_id is not None
            else None
        )
        edition = services.set_poster(self.edition, poster, actor=_actor(request))
        return Response(PosterSerializer(self._payload(edition)).data)


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
    """Données des gabarits et des sections « données » : une seule lecture de l'édition."""
    poster = edition.poster if edition.poster_id else None
    return {
        "edition": PublicEditionSerializer(edition).data,
        "poster": PublicFileRefSerializer(poster).data if poster and poster.published else None,
        "documents": PublicFileRefSerializer(services.public_documents(edition), many=True).data,
        "committees": services.public_committees(edition),
        # Origine publique (adresses canoniques, Open Graph, plan du site : E7).
        "site_url": settings.GESTCONF_PUBLIC_URL,
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


class PublicFileView(_PublicPortalView):
    """``GET /v1/public/files/<uuid>/<nom>`` : fichier public, s'il est publié et dans un
    contexte public (``services.is_publicly_served``), sinon 404 (rien n'est révélé).

    Jamais servi par Apache (stockage hors racine web). ``nosniff`` ; documents en
    ``attachment`` ; CSP ``sandbox`` ; cache public court, ETag = empreinte SHA-256.
    """

    @extend_schema(
        operation_id="public_file",
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
        auth=[],
    )
    def get(self, request: Request, uuid, name: str):
        public_file = PublicFile.objects.filter(uuid=uuid).first()
        if public_file is None or not services.is_publicly_served(public_file):
            raise Http404
        etag = f'"{public_file.sha256}"'
        if request.headers.get("If-None-Match") == etag:
            response = HttpResponse(status=304)
        else:
            try:
                data = public_files.read(public_file)
            except FileNotFoundError as exc:  # ligne sans fichier : signalé par check_integrity
                raise Http404 from exc
            response = HttpResponse(data, content_type=public_file.content_type)
            download = public_files.safe_download_name(
                public_file.original_name, public_file.extension
            )
            disposition = "inline" if public_file.kind != PublicFileKind.DOCUMENT else "attachment"
            response["Content-Disposition"] = f'{disposition}; filename="{download}"'
            response["Content-Length"] = str(len(data))
        response["ETag"] = etag
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "public, max-age=3600"
        return response


class PublicSiteView(_PublicPortalView):
    """Données des gabarits des pages du site, en un appel."""

    @extend_schema(
        operation_id="public_portal_site", responses={200: PublicSiteSerializer}, auth=[]
    )
    def get(self, request: Request) -> Response:
        return self.respond(_site_data(self.edition()))
