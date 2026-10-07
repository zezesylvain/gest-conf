"""Routes des annonces et envois groupés (plan L8, N10 et N11).

- gestion ``v1/manage/editions/{id}/…`` (2FA) : ``communications.send`` (administrateur,
  Chair, CO « communication ») ; toute publication exige une **réauthentification
  récente** (RG-22) ;
- public : bandeau de dernière minute (lu dans le navigateur, réponse minimale, cache de
  60 s, limité en débit), actualités (lues au build du portail), désabonnement par jeton
  signé ;
- compte : abonnement aux annonces d'une édition.
"""

from __future__ import annotations

from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.communications import announcements as service
from apps.communications.announcement_serializers import (
    AnnouncementDetailSerializer,
    AnnouncementPreviewSerializer,
    AnnouncementSerializer,
    AnnouncementWriteSerializer,
    CancelledCountSerializer,
    PublicBannerSerializer,
    PublicNewsItemSerializer,
    SegmentSerializer,
    SubscriptionSerializer,
    UnsubscribedSerializer,
    UnsubscribeSerializer,
    announcement_data,
    public_banner_data,
)
from apps.communications.models import Announcement
from apps.communications.segments import available_segments, recipients
from apps.conferences.models import Edition
from apps.conferences.services import current_public_edition
from apps.core.actor import Actor
from apps.core.permissions import CsrfEnforced

BANNER_CACHE = "public, max-age=60"
NEWS_CACHE = "public, max-age=300"


class _CommunicationViewSet(ManageViewSet):
    pagination_class = None
    filter_backends = ()

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset(self.access.capabilities)


class SegmentViewSet(_CommunicationViewSet):
    """``…/segments`` : catalogue autorisé et nombre de destinataires de chaque segment."""

    serializer_class = SegmentSerializer
    required_capabilities = {"list": C.COMMUNICATIONS_SEND}

    @extend_schema(
        operation_id="manage_segments_list", responses={200: SegmentSerializer(many=True)}
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = [
            {
                "code": segment.code,
                "label": str(segment.label),
                "recipients": recipients(self.edition, segment).count(),
            }
            for segment in available_segments(self.capabilities)
        ]
        return Response(SegmentSerializer(rows, many=True).data)


class AnnouncementViewSet(_CommunicationViewSet):
    """``…/announcements`` : annonces (brouillon, aperçu, essai, publication, retrait)."""

    serializer_class = AnnouncementSerializer
    required_capabilities = {
        "list": C.COMMUNICATIONS_SEND,
        "create": C.COMMUNICATIONS_SEND,
        "retrieve": C.COMMUNICATIONS_SEND,
        "partial_update": C.COMMUNICATIONS_SEND,
        "destroy": C.COMMUNICATIONS_SEND,
        "preview": C.COMMUNICATIONS_SEND,
        "test": C.COMMUNICATIONS_SEND,
        "publish": C.COMMUNICATIONS_SEND,
        "withdraw": C.COMMUNICATIONS_SEND,
        "cancel": C.COMMUNICATIONS_SEND,
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        # Toute publication se confirme par une réauthentification récente : une annonce peut
        # partir à tout un segment (RG-22), et le bandeau s'affiche aussitôt.
        if self.action == "publish":
            permissions.append(RecentAuthRequired())
        return permissions

    def announcement(self, announcement_id: int) -> Announcement:
        announcement = (
            Announcement.objects.filter(pk=announcement_id, edition=self.edition)
            .select_related("edition")
            .first()
        )
        if announcement is None:
            raise Http404
        return announcement

    def detail_response(self, announcement: Announcement, code: int = 200) -> Response:
        data = {**announcement_data(announcement), "sending": service.sending_stats(announcement)}
        return Response(AnnouncementDetailSerializer(data).data, status=code)

    @extend_schema(
        operation_id="manage_announcements_list",
        responses={200: AnnouncementSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        rows = Announcement.objects.filter(edition=self.edition).select_related("edition")
        return Response(
            AnnouncementSerializer(
                [announcement_data(row) for row in rows.order_by("-created_at", "-id")], many=True
            ).data
        )

    @extend_schema(
        operation_id="manage_announcements_create",
        request=AnnouncementWriteSerializer,
        responses={201: AnnouncementDetailSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = AnnouncementWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = service.create_announcement(
            self.edition,
            serializer.validated_data,
            capabilities=self.capabilities,
            actor=self.actor(),
        )
        return self.detail_response(announcement, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_announcements_retrieve",
        responses={200: AnnouncementDetailSerializer},
    )
    def retrieve(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        return self.detail_response(self.announcement(announcement_id))

    @extend_schema(
        operation_id="manage_announcements_update",
        request=AnnouncementWriteSerializer,
        responses={200: AnnouncementDetailSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        serializer = AnnouncementWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        announcement = service.update_announcement(
            self.announcement(announcement_id),
            serializer.validated_data,
            capabilities=self.capabilities,
            actor=self.actor(),
        )
        return self.detail_response(announcement)

    @extend_schema(operation_id="manage_announcements_destroy", responses={204: None})
    def destroy(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        service.delete_announcement(self.announcement(announcement_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_announcements_preview",
        parameters=[OpenApiParameter("locale", str, enum=["fr", "en"])],
        responses={200: AnnouncementPreviewSerializer},
    )
    def preview(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        announcement = self.announcement(announcement_id)
        locale = "en" if request.query_params.get("locale") == "en" else "fr"
        data = service.preview(announcement, request.user, locale)
        return Response(AnnouncementPreviewSerializer(data).data)

    @extend_schema(operation_id="manage_announcements_test", request=None, responses={202: None})
    def test(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        service.send_test(self.announcement(announcement_id), actor=self.actor())
        return Response(status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        operation_id="manage_announcements_publish",
        request=None,
        responses={200: AnnouncementDetailSerializer},
    )
    def publish(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        announcement = service.publish(
            self.announcement(announcement_id),
            capabilities=self.capabilities,
            actor=self.actor(),
        )
        return self.detail_response(announcement)

    @extend_schema(
        operation_id="manage_announcements_withdraw",
        request=None,
        responses={200: AnnouncementDetailSerializer},
    )
    def withdraw(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        announcement = service.withdraw(self.announcement(announcement_id), actor=self.actor())
        return self.detail_response(announcement)

    @extend_schema(
        operation_id="manage_announcements_cancel",
        request=None,
        responses={200: CancelledCountSerializer},
    )
    def cancel(self, request: Request, edition_id: int, announcement_id: int) -> Response:
        cancelled = service.cancel_sending(self.announcement(announcement_id), actor=self.actor())
        return Response(CancelledCountSerializer({"cancelled": cancelled}).data)


# --- Public ------------------------------------------------------------------------------


class PublicBannerView(APIView):
    """``GET /v1/public/portal/banner`` : bandeau actif de l'édition publique courante, lu
    dans le navigateur (jamais pré-rendu) ; réponse minimale."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "portal_banner"

    @extend_schema(operation_id="public_banner", responses={200: PublicBannerSerializer}, auth=[])
    def get(self, request: Request) -> Response:
        edition = current_public_edition()
        banner = service.active_banner(edition) if edition is not None else None
        response = Response(PublicBannerSerializer(public_banner_data(banner)).data)
        response["Cache-Control"] = BANNER_CACHE
        return response


class PublicNewsView(APIView):
    """``GET /v1/public/news`` : actualités publiées de l'édition publique courante ; lu au
    build du portail (page « Actualités », pré-rendue)."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    @extend_schema(
        operation_id="public_news", responses={200: PublicNewsItemSerializer(many=True)}, auth=[]
    )
    def get(self, request: Request) -> Response:
        edition = current_public_edition()
        if edition is None:
            raise Http404
        response = Response(PublicNewsItemSerializer(service.news(edition), many=True).data)
        response["Cache-Control"] = NEWS_CACHE
        return response


class UnsubscribeView(APIView):
    """``POST /v1/public/announcements/unsubscribe`` : lien du pied de page des annonces
    (jeton signé, sans connexion) ; limité en débit."""

    permission_classes = (AllowAny, CsrfEnforced)
    throttle_scope = "announcement_unsubscribe"

    @extend_schema(
        operation_id="public_announcements_unsubscribe",
        request=UnsubscribeSerializer,
        responses={200: UnsubscribedSerializer},
        auth=[],
    )
    def post(self, request: Request) -> Response:
        serializer = UnsubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edition = service.unsubscribe(
            serializer.validated_data["token"], actor=Actor.from_request(request)
        )
        response = Response(
            UnsubscribedSerializer(
                {"edition_title_fr": edition.title_fr, "edition_title_en": edition.title_en}
            ).data
        )
        response["Cache-Control"] = "no-store"
        return response


# --- Compte ------------------------------------------------------------------------------


class MySubscriptionView(APIView):
    """``/v1/me/editions/{id}/announcements`` : recevoir ou non les annonces par e-mail."""

    permission_classes = (IsAuthenticated,)

    def edition(self, edition_id: int) -> Edition:
        edition = Edition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise Http404
        return edition

    @extend_schema(
        operation_id="me_announcements_subscription",
        responses={200: SubscriptionSerializer},
    )
    def get(self, request: Request, edition_id: int) -> Response:
        subscribed = service.is_subscribed(request.user, self.edition(edition_id))
        return Response(SubscriptionSerializer({"subscribed": subscribed}).data)

    @extend_schema(
        operation_id="me_announcements_subscription_update",
        request=SubscriptionSerializer,
        responses={200: SubscriptionSerializer},
    )
    def put(self, request: Request, edition_id: int) -> Response:
        serializer = SubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        subscribed = service.set_subscription(
            request.user,
            self.edition(edition_id),
            subscribed=serializer.validated_data["subscribed"],
            actor=Actor.from_request(request),
        )
        return Response(SubscriptionSerializer({"subscribed": subscribed}).data)
