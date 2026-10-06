"""Routes de l'évaluation (plan L4 §4). Les routes servies aux relecteurs sont nommées
« reviewer-… » : un test vérifie qu'elles ont toutes leur test de fuite RG-04."""

from django.urls import path

from apps.reviews.manage_views import AssignmentViewSet as A
from apps.reviews.manage_views import ConflictViewSet as K
from apps.reviews.manage_views import GridViewSet as G
from apps.reviews.manage_views import ReviewSubmissionViewSet as RS

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
    # Recevabilité et affectations (président du CS, L4.2).
    path(
        f"{E}/review-submissions",
        RS.as_view({"get": "list"}),
        name="manage-review-submissions-list",
    ),
    path(
        f"{E}/review-submissions/<int:submission_id>",
        RS.as_view({"get": "retrieve"}),
        name="manage-review-submissions-detail",
    ),
    path(
        f"{E}/review-submissions/<int:submission_id>/screening",
        RS.as_view({"post": "screening"}),
        name="manage-review-submissions-screening",
    ),
    path(
        f"{E}/review-submissions/<int:submission_id>/candidates",
        RS.as_view({"get": "candidates"}),
        name="manage-review-submissions-candidates",
    ),
    path(f"{E}/assignments", A.as_view({"post": "create"}), name="manage-assignments-list"),
    path(
        f"{E}/assignments/<int:assignment_id>",
        A.as_view({"patch": "partial_update"}),
        name="manage-assignments-detail",
    ),
    path(
        f"{E}/assignments/<int:assignment_id>/cancel",
        A.as_view({"post": "cancel"}),
        name="manage-assignments-cancel",
    ),
    path(f"{E}/conflicts", K.as_view({"post": "create"}), name="manage-conflicts-list"),
]
