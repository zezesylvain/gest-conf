from django.urls import path

from apps.accounts.views import ConsentsView, MeView, PreferencesView, ProfileView

app_name = "accounts"

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("me/preferences", PreferencesView.as_view(), name="me-preferences"),
    path("me/profile", ProfileView.as_view(), name="me-profile"),
    path("me/consents", ConsentsView.as_view(), name="me-consents"),
]
