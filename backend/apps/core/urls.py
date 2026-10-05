from django.urls import path

from apps.core.views import HealthView, request_diagnostics

app_name = "core"

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    # Désactivé par défaut (404) : voir request_diagnostics.
    path("diagnostics/request", request_diagnostics, name="diagnostics-request"),
]
