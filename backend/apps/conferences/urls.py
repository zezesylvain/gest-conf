"""Routes du paramétrage (``v1/manage/editions/…``) et de l'édition publique (plan L1 §9.3)."""

from django.urls import path

from apps.conferences import views

app_name = "conferences"

E = "manage/editions/<int:edition_id>"


def _child_routes(prefix: str, viewset, name: str) -> list:
    return [
        path(
            f"{E}/{prefix}",
            viewset.as_view({"get": "list", "post": "create"}),
            name=f"manage-{name}-list",
        ),
        path(
            f"{E}/{prefix}/<int:item_id>",
            viewset.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
            name=f"manage-{name}-detail",
        ),
    ]


urlpatterns = [
    path("manage/editions", views.ManageEditionListView.as_view(), name="manage-editions"),
    path(
        E,
        views.EditionViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-edition",
    ),
    path(
        f"{E}/status",
        views.EditionStatusViewSet.as_view({"post": "create"}),
        name="manage-edition-status",
    ),
    path(
        f"{E}/confidentiality",
        views.ConfidentialityViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-confidentiality",
    ),
    *_child_routes("tracks", views.TrackViewSet, "tracks"),
    *_child_routes("submission-types", views.SubmissionTypeViewSet, "submission-types"),
    *_child_routes("key-dates", views.KeyDateViewSet, "key-dates"),
    path(
        "public/editions/current",
        views.PublicCurrentEditionView.as_view(),
        name="public-current-edition",
    ),
]
