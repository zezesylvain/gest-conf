from django.urls import path

from apps.accounts import manage_views
from apps.accounts.views import (
    ConsentsView,
    MeView,
    PreferencesView,
    ProfileView,
    TotpQrView,
)

app_name = "accounts"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("me/preferences", PreferencesView.as_view(), name="me-preferences"),
    path("me/profile", ProfileView.as_view(), name="me-profile"),
    path("me/consents", ConsentsView.as_view(), name="me-consents"),
    path("me/totp-qr", TotpQrView.as_view(), name="me-totp-qr"),
    # Membres, invitations et journal d'une édition (plan L1 §9.3).
    path(
        f"{E}/roles",
        manage_views.MemberViewSet.as_view({"get": "list"}),
        name="manage-roles",
    ),
    path(
        f"{E}/roles/<int:role_id>/revoke",
        manage_views.MemberViewSet.as_view({"post": "revoke"}),
        name="manage-role-revoke",
    ),
    path(
        f"{E}/invitations",
        manage_views.InvitationViewSet.as_view({"get": "list", "post": "create"}),
        name="manage-invitations",
    ),
    path(
        f"{E}/invitations/<int:invitation_id>/resend",
        manage_views.InvitationViewSet.as_view({"post": "resend"}),
        name="manage-invitation-resend",
    ),
    path(
        f"{E}/invitations/<int:invitation_id>/cancel",
        manage_views.InvitationViewSet.as_view({"post": "cancel"}),
        name="manage-invitation-cancel",
    ),
    path(
        f"{E}/audit",
        manage_views.AuditViewSet.as_view({"get": "list"}),
        name="manage-audit",
    ),
    # Réponse aux invitations (RG-20, §5.7).
    path(
        "invitations/lookup", manage_views.InvitationLookupView.as_view(), name="invitation-lookup"
    ),
    path(
        "invitations/accept", manage_views.InvitationAcceptView.as_view(), name="invitation-accept"
    ),
    path(
        "invitations/decline",
        manage_views.InvitationDeclineView.as_view(),
        name="invitation-decline",
    ),
    path(
        "invitations/link-email",
        manage_views.InvitationLinkEmailView.as_view(),
        name="invitation-link-email",
    ),
]
