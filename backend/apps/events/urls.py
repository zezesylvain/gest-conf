"""Routes du jour J et des attestations (plan L7 §4)."""

from django.urls import path

from apps.events import views

app_name = "events"

E = "manage/editions/<int:edition_id>"

CHECKIN = views.CheckinViewSet
BADGES = views.BadgeViewSet

urlpatterns = [
    path(
        f"{E}/signature",
        views.SignatureViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-signature",
    ),
    path(
        f"{E}/signature/image",
        views.SignatureImageViewSet.as_view({"get": "image", "put": "upload_image"}),
        name="manage-signature-image",
    ),
    path(f"{E}/checkin", CHECKIN.as_view({"get": "list"}), name="manage-checkin"),
    path(f"{E}/checkin/scan", CHECKIN.as_view({"post": "scan"}), name="manage-checkin-scan"),
    path(f"{E}/checkin/manual", CHECKIN.as_view({"post": "manual"}), name="manage-checkin-manual"),
    path(f"{E}/checkin/bundle", CHECKIN.as_view({"get": "bundle"}), name="manage-checkin-bundle"),
    path(f"{E}/checkin/sync", CHECKIN.as_view({"post": "sync"}), name="manage-checkin-sync"),
    path(
        f"{E}/checkin/summary",
        CHECKIN.as_view({"get": "summary"}),
        name="manage-checkin-summary",
    ),
    path(f"{E}/checkin/export", CHECKIN.as_view({"get": "export"}), name="manage-checkin-export"),
    path(
        f"{E}/checkin/<int:checkin_id>/cancel",
        CHECKIN.as_view({"post": "cancel"}),
        name="manage-checkin-cancel",
    ),
    path(
        f"{E}/registrations/badges",
        BADGES.as_view({"get": "sheets"}),
        name="manage-badges",
    ),
    path(
        f"{E}/registrations/badges/batches",
        BADGES.as_view({"get": "batches"}),
        name="manage-badges-batches",
    ),
    path(
        f"{E}/registrations/<int:registration_id>/badge",
        BADGES.as_view({"get": "single"}),
        name="manage-badge",
    ),
    path(
        f"{E}/registrations/<int:registration_id>/regenerate-token",
        BADGES.as_view({"post": "regenerate"}),
        name="manage-badge-regenerate",
    ),
    path(
        "registrations/<int:registration_id>/badge",
        views.MyBadgeView.as_view(),
        name="registrations-badge",
    ),
]
