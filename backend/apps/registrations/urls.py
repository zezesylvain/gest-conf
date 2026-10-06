"""Routes des inscriptions (plan L6 §4)."""

from django.urls import path

from apps.registrations import views

app_name = "registrations"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(
        f"{E}/registrations/settings",
        views.RegistrationSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-registration-settings",
    ),
]
