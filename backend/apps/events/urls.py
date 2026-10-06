"""Routes du jour J et des attestations (plan L7 §4)."""

from django.urls import path

from apps.events import views

app_name = "events"

E = "manage/editions/<int:edition_id>"

CHECKIN = views.CheckinViewSet
BADGES = views.BadgeViewSet
DAY = views.DaySessionViewSet
CERT = f"{E}/certificates"
S = f"{E}/day/sessions/<int:session_id>"

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
    path(f"{E}/day/sessions", DAY.as_view({"get": "sessions"}), name="manage-day-sessions"),
    path(f"{S}/attendance", DAY.as_view({"get": "attendance"}), name="manage-day-attendance"),
    path(
        f"{S}/attendance/scan",
        DAY.as_view({"post": "attendance_scan"}),
        name="manage-day-attendance-scan",
    ),
    path(
        f"{S}/attendance/export",
        DAY.as_view({"get": "attendance_export"}),
        name="manage-day-attendance-export",
    ),
    path(
        f"{S}/slots/<int:slot_id>/presented",
        DAY.as_view({"post": "presented"}),
        name="manage-day-presented",
    ),
    path(
        f"{S}/slots/<int:slot_id>/unpresented",
        DAY.as_view({"post": "unpresented"}),
        name="manage-day-unpresented",
    ),
    path(
        f"{CERT}/settings",
        views.CertificateSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-certificate-settings",
    ),
    path(
        f"{CERT}/settings/header",
        views.CertificateFilesViewSet.as_view(
            {"get": "header", "put": "upload_header", "delete": "delete_header"}
        ),
        name="manage-certificate-header",
    ),
    path(
        f"{CERT}/settings/signing-key",
        views.CertificateFilesViewSet.as_view({"put": "upload_key", "delete": "delete_key"}),
        name="manage-certificate-signing-key",
    ),
    path(
        f"{CERT}/templates",
        views.DocumentTemplateViewSet.as_view({"get": "list"}),
        name="manage-certificate-templates",
    ),
    path(
        f"{CERT}/templates/<str:nature>",
        views.DocumentTemplateViewSet.as_view({"patch": "partial_update"}),
        name="manage-certificate-template",
    ),
    path(
        f"{CERT}/templates/<str:nature>/preview",
        views.DocumentTemplateViewSet.as_view({"get": "preview"}),
        name="manage-certificate-preview",
    ),
    path(
        f"{CERT}/signatories",
        views.DocumentTemplateViewSet.as_view({"get": "signatories"}),
        name="manage-certificate-signatories",
    ),
    path(
        f"{CERT}/overview",
        views.CertificateViewSet.as_view({"get": "overview"}),
        name="manage-certificates-overview",
    ),
    path(
        f"{CERT}/issue",
        views.CertificateViewSet.as_view({"post": "issue"}),
        name="manage-certificates-issue",
    ),
    path(f"{CERT}", views.CertificateViewSet.as_view({"get": "list"}), name="manage-certificates"),
    path(
        f"{CERT}/<int:certificate_id>/pdf",
        views.CertificateViewSet.as_view({"get": "pdf"}),
        name="manage-certificate-pdf",
    ),
    path(
        f"{CERT}/<int:certificate_id>/revoke",
        views.CertificateViewSet.as_view({"post": "revoke"}),
        name="manage-certificate-revoke",
    ),
    path("me/certificates", views.MyCertificatesView.as_view(), name="me-certificates"),
    path(
        "me/certificates/<int:certificate_id>/pdf",
        views.MyCertificatePdfView.as_view(),
        name="me-certificate-pdf",
    ),
    path(
        "public/certificates/<str:code>",
        views.PublicCertificateView.as_view(),
        name="public-certificate",
    ),
]
