"""Routes de l'espace auteur et de la gestion des soumissions (plan L3 §4)."""

from django.urls import path

from apps.submissions.manage_views import SubmissionManageViewSet as M
from apps.submissions.views import SubmissionFileViewSet as F
from apps.submissions.views import SubmissionViewSet as V

app_name = "submissions"

S = "submissions/<int:submission_id>"
E = "manage/editions/<int:edition_id>/submissions"
MS = f"{E}/<int:submission_id>"

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
    path(f"{S}/final-version", F.as_view({"post": "final_version"}), name="final-version"),
    path(
        f"{S}/confirm-presentation",
        V.as_view({"post": "confirm_presentation"}),
        name="confirm-presentation",
    ),
    path(
        f"{S}/final-version/content",
        V.as_view({"get": "final_version_content"}),
        name="final-version-content",
    ),
    # Gestion : routes d'action avant le détail (« stats », « export » ne sont pas des id).
    path(E, M.as_view({"get": "list"}), name="manage-submissions-list"),
    path(f"{E}/stats", M.as_view({"get": "stats"}), name="manage-submissions-stats"),
    path(f"{E}/export", M.as_view({"get": "export"}), name="manage-submissions-export"),
    path(MS, M.as_view({"get": "retrieve"}), name="manage-submissions-detail"),
    path(
        f"{MS}/files/<int:file_id>/content",
        M.as_view({"get": "file_content"}),
        name="manage-submissions-file-content",
    ),
    path(
        f"{MS}/extensions",
        M.as_view({"post": "grant_extension"}),
        name="manage-submissions-extensions",
    ),
    path(
        f"{MS}/extensions/<int:extension_id>/revoke",
        M.as_view({"post": "revoke_extension"}),
        name="manage-submissions-extension-revoke",
    ),
]
