"""Routes de l'évaluation (plan L4 §4). Les routes servies aux relecteurs sont nommées
« reviewer-… » : un test vérifie qu'elles ont toutes leur test de fuite RG-04."""

from django.urls import path

from apps.reviews.manage_views import GridViewSet as G

app_name = "reviews"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(f"{E}/grids", G.as_view({"get": "list", "post": "create"}), name="manage-grids-list"),
    path(
        f"{E}/grids/<int:grid_id>",
        G.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="manage-grids-detail",
    ),
    path(
        f"{E}/grids/<int:grid_id>/duplicate",
        G.as_view({"post": "duplicate"}),
        name="manage-grids-duplicate",
    ),
]
