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
    path(
        f"{E}/billing/documents",
        views.BillingDocumentsViewSet.as_view({"get": "list"}),
        name="manage-billing-documents",
    ),
    path(
        f"{E}/billing/documents/issue-pending",
        views.IssuePendingInvoicesViewSet.as_view({"post": "create"}),
        name="manage-billing-issue-pending",
    ),
    path(
        f"{E}/registrations/<int:item_id>/payments",
        views.ManualPaymentViewSet.as_view({"post": "create"}),
        name="manage-registration-payments",
    ),
    path(
        f"{E}/registrations/<int:item_id>/refunds",
        views.RefundViewSet.as_view({"post": "create"}),
        name="manage-registration-refunds",
    ),
    path(
        f"{E}/registrations/<int:item_id>/proforma",
        views.ProformaViewSet.as_view({"post": "create"}),
        name="manage-registration-proforma",
    ),
    path(
        f"{E}/registrations/<int:item_id>/documents/<int:document_id>",
        views.RegistrationDocumentViewSet.as_view({"get": "retrieve"}),
        name="manage-registration-document",
    ),
    path(
        "registrations/<int:registration_id>/documents/<int:document_id>",
        views.MyDocumentView.as_view(),
        name="registration-document",
    ),
    path(
        "registrations/<int:registration_id>/proforma",
        views.MyProformaView.as_view(),
        name="registration-proforma",
    ),
    path(
        "registrations/<int:registration_id>/pay",
        views.MyPaymentView.as_view(),
        name="registration-pay",
    ),
    path(
        "registrations/<int:registration_id>/payment-check",
        views.MyPaymentCheckView.as_view(),
        name="registration-payment-check",
    ),
    path(
        "payments/webhook/<str:provider>",
        views.PaymentWebhookView.as_view(),
        name="payments-webhook",
    ),
    path("payments/fake/<str:reference>", views.FakeCheckoutView.as_view(), name="payments-fake"),
]
