"""Routes du programme (plan L5 §4)."""

from django.urls import path

from apps.program import views

app_name = "program"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(
        f"{E}/program/settings",
        views.ProgramSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-program-settings",
    ),
]
