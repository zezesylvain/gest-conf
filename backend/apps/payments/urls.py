"""Routes des paiements et de la facturation (plan L6 §4)."""

from django.urls import path

from apps.payments import views

app_name = "payments"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(
        f"{E}/billing/profile",
        views.BillingProfileViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-billing-profile",
    ),
]
