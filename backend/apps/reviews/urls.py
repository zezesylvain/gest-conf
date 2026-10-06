"""Routes de l'évaluation (plan L4 §4). Les routes servies aux relecteurs sont nommées
« reviewer-… » : un test vérifie qu'elles ont toutes leur test de fuite RG-04."""

from django.urls import path

from apps.reviews.manage_views import AssignmentViewSet as A
from apps.reviews.manage_views import ConflictViewSet as K
from apps.reviews.manage_views import GridViewSet as G
from apps.reviews.manage_views import ReviewProgressViewSet as P
from apps.reviews.manage_views import ReviewSubmissionViewSet as RS
from apps.reviews.reviewer_views import ExpertiseViewSet as X
from apps.reviews.reviewer_views import ReviewerAssignmentViewSet as RA

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
    path(
        f"{E}/review-submissions/<int:submission_id>/reviews",
        RS.as_view({"get": "reviews"}),
        name="manage-review-submissions-reviews",
    ),
    path(
        f"{E}/review-submissions/<int:submission_id>/discussion/open",
        RS.as_view({"post": "open_discussion"}),
        name="manage-review-submissions-discussion-open",
    ),
    path(
        f"{E}/review-submissions/<int:submission_id>/discussion/messages",
        RS.as_view({"post": "post_message"}),
        name="manage-review-submissions-discussion-messages",
    ),
    path(f"{E}/review-progress", P.as_view({"get": "progress"}), name="manage-review-progress"),
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
    # Espace relecteur (L4.3) : routes « reviewer-… », chacune couverte par un test de fuite.
    path(f"{E}/reviews/assignments", RA.as_view({"get": "list"}), name="reviewer-assignments-list"),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>",
        RA.as_view({"get": "retrieve"}),
        name="reviewer-assignments-detail",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/file",
        RA.as_view({"get": "file"}),
        name="reviewer-assignments-file",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/authors",
        RA.as_view({"get": "authors"}),
        name="reviewer-assignments-authors",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/decline",
        RA.as_view({"post": "decline"}),
        name="reviewer-assignments-decline",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/review",
        RA.as_view({"put": "save_review"}),
        name="reviewer-review",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/review/submit",
        RA.as_view({"post": "submit_review"}),
        name="reviewer-review-submit",
    ),
    path(
        f"{E}/reviews/assignments/<int:assignment_id>/discussion",
        RA.as_view({"get": "discussion", "post": "post_message"}),
        name="reviewer-discussion",
    ),
    path(
        f"{E}/reviews/expertise",
        X.as_view({"get": "retrieve", "put": "update"}),
        name="reviewer-expertise",
    ),
]
