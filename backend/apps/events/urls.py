"""Routes du jour J et des attestations (plan L7 §4)."""

from django.urls import path

from apps.events import views

app_name = "events"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(
        f"{E}/signature",
        views.SignatureViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-signature",
    ),
    path(
        f"{E}/signature/image",
        views.SignatureImageViewSet.as_view({"get": "image", "put": "upload_image"}),
        name="manage-signature-image",
    ),
]
