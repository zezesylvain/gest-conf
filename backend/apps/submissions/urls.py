"""Routes de l'espace auteur (plan L3 §4)."""

from django.urls import path

from apps.submissions.views import SubmissionFileViewSet as F
from apps.submissions.views import SubmissionViewSet as V

app_name = "submissions"

S = "submissions/<int:submission_id>"

urlpatterns = [
    path("submissions", V.as_view({"get": "list", "post": "create"}), name="list"),
    path(
        S,
        V.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="detail",
    ),
    path(f"{S}/authors", V.as_view({"put": "authors"}), name="authors"),
    path(f"{S}/file", F.as_view({"post": "upload", "delete": "remove_file"}), name="file"),
    path(f"{S}/file/content", V.as_view({"get": "file_content"}), name="file-content"),
    path(f"{S}/check", V.as_view({"get": "check"}), name="check"),
    path(f"{S}/submit", V.as_view({"post": "submit"}), name="submit"),
    path(f"{S}/withdraw", V.as_view({"post": "withdraw"}), name="withdraw"),
    path(f"{S}/timeline", V.as_view({"get": "timeline"}), name="timeline"),
]
