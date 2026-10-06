"""Routes du programme (plan L5 §4)."""

from django.urls import path

from apps.program import views

app_name = "program"

E = "manage/editions/<int:edition_id>"

P = f"{E}/program"

urlpatterns = [
    path(
        P,
        views.ProgramBoardViewSet.as_view({"get": "retrieve"}),
        name="manage-program",
    ),
    path(
        f"{P}/rooms",
        views.RoomViewSet.as_view({"post": "create"}),
        name="manage-program-rooms",
    ),
    path(
        f"{P}/rooms/<int:item_id>",
        views.RoomViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-program-room",
    ),
    path(
        f"{P}/sessions",
        views.SessionViewSet.as_view({"post": "create"}),
        name="manage-program-sessions",
    ),
    path(
        f"{P}/sessions/<int:item_id>",
        views.SessionViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-program-session",
    ),
    path(
        f"{P}/sessions/<int:session_id>/slots",
        views.SlotViewSet.as_view({"post": "create"}),
        name="manage-program-slots",
    ),
    path(
        f"{P}/slots/<int:item_id>",
        views.SlotViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-program-slot",
    ),
    path(
        f"{P}/sessions/<int:session_id>/roles",
        views.SessionRoleViewSet.as_view({"post": "create"}),
        name="manage-program-roles",
    ),
    path(
        f"{P}/session-roles/<int:item_id>",
        views.SessionRoleViewSet.as_view({"delete": "destroy"}),
        name="manage-program-role",
    ),
    path(
        f"{P}/people",
        views.ProgramPeopleViewSet.as_view({"get": "list"}),
        name="manage-program-people",
    ),
    path(
        f"{E}/program/settings",
        views.ProgramSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-program-settings",
    ),
]
