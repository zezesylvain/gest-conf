"""Routes de la cloche (plan L3, F13) et des annonces (plan L8, N10 et N11)."""

from django.urls import path

from apps.communications import announcement_views as announcements
from apps.communications.views import NotificationsReadView, NotificationsView

app_name = "communications"

E = "manage/editions/<int:edition_id>"
ANNOUNCEMENTS = announcements.AnnouncementViewSet
A = f"{E}/announcements/<int:announcement_id>"

urlpatterns = [
    path("me/notifications", NotificationsView.as_view(), name="me-notifications"),
    path("me/notifications/read", NotificationsReadView.as_view(), name="me-notifications-read"),
    path(
        "me/editions/<int:edition_id>/announcements",
        announcements.MySubscriptionView.as_view(),
        name="me-announcements",
    ),
    path(
        f"{E}/segments",
        announcements.SegmentViewSet.as_view({"get": "list"}),
        name="manage-segments",
    ),
    path(
        f"{E}/announcements",
        ANNOUNCEMENTS.as_view({"get": "list", "post": "create"}),
        name="manage-announcements",
    ),
    path(
        A,
        ANNOUNCEMENTS.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="manage-announcement",
    ),
    path(
        f"{A}/preview",
        ANNOUNCEMENTS.as_view({"get": "preview"}),
        name="manage-announcement-preview",
    ),
    path(f"{A}/test", ANNOUNCEMENTS.as_view({"post": "test"}), name="manage-announcement-test"),
    path(
        f"{A}/publish",
        ANNOUNCEMENTS.as_view({"post": "publish"}),
        name="manage-announcement-publish",
    ),
    path(
        f"{A}/withdraw",
        ANNOUNCEMENTS.as_view({"post": "withdraw"}),
        name="manage-announcement-withdraw",
    ),
    path(
        f"{A}/cancel",
        ANNOUNCEMENTS.as_view({"post": "cancel"}),
        name="manage-announcement-cancel",
    ),
    path("public/portal/banner", announcements.PublicBannerView.as_view(), name="public-banner"),
    path("public/news", announcements.PublicNewsView.as_view(), name="public-news"),
    path(
        "public/announcements/unsubscribe",
        announcements.UnsubscribeView.as_view(),
        name="public-unsubscribe",
    ),
]
