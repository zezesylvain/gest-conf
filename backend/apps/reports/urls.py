"""Routes des rapports (plan L8, N13) et du fil d'activité (N14)."""

from django.urls import path

from apps.reports import views

app_name = "reports"

E = "manage/editions/<int:edition_id>"
REPORTS = views.ReportViewSet

urlpatterns = [
    path(f"{E}/reports", REPORTS.as_view({"get": "list"}), name="manage-reports"),
    path(f"{E}/reports/<slug:section>", REPORTS.as_view({"get": "retrieve"}), name="manage-report"),
    path(
        f"{E}/reports/<slug:section>/export",
        REPORTS.as_view({"get": "export"}),
        name="manage-report-export",
    ),
    path(
        f"{E}/activity",
        views.ActivityViewSet.as_view({"get": "list"}),
        name="manage-activity",
    ),
]
