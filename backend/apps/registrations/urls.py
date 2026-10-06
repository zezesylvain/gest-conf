"""Routes des inscriptions (plan L6 §4)."""

from django.urls import path

from apps.registrations import manage_views, views

app_name = "registrations"

E = "manage/editions/<int:edition_id>"

urlpatterns = [
    path(
        f"{E}/registrations/settings",
        views.RegistrationSettingsViewSet.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-registration-settings",
    ),
    path(
        f"{E}/registrations/categories",
        views.CategoryViewSet.as_view({"get": "list", "post": "create"}),
        name="manage-registration-categories",
    ),
    path(
        f"{E}/registrations/categories/<int:item_id>",
        views.CategoryViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-registration-category",
    ),
    path(
        f"{E}/registrations/categories/<int:item_id>/fees",
        views.CategoryViewSet.as_view({"put": "fees"}),
        name="manage-registration-category-fees",
    ),
    path(
        f"{E}/registrations/options",
        views.OptionViewSet.as_view({"get": "list", "post": "create"}),
        name="manage-registration-options",
    ),
    path(
        f"{E}/registrations/options/<int:item_id>",
        views.OptionViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-registration-option",
    ),
    path(
        f"{E}/registrations/promo-codes",
        views.PromoCodeViewSet.as_view({"get": "list", "post": "create"}),
        name="manage-registration-promo-codes",
    ),
    path(
        f"{E}/registrations/promo-codes/<int:item_id>",
        views.PromoCodeViewSet.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-registration-promo-code",
    ),
    path(
        f"{E}/registrations",
        manage_views.RegistrationListViewSet.as_view({"get": "list", "post": "create"}),
        name="manage-registrations",
    ),
    path(
        f"{E}/registrations/<int:item_id>",
        manage_views.RegistrationDetailViewSet.as_view({"get": "retrieve"}),
        name="manage-registration",
    ),
    path(
        f"{E}/registrations/<int:item_id>/cancel",
        manage_views.RegistrationDetailViewSet.as_view({"post": "cancel"}),
        name="manage-registration-cancel",
    ),
    path(
        f"{E}/registrations/<int:item_id>/waive",
        manage_views.RegistrationDetailViewSet.as_view({"post": "waive"}),
        name="manage-registration-waive",
    ),
    path(
        f"{E}/registrations/<int:item_id>/proof",
        manage_views.RegistrationDetailViewSet.as_view({"get": "proof"}),
        name="manage-registration-proof",
    ),
    path("public/registration", views.PublicRegistrationView.as_view(), name="public-registration"),
    path("registrations", views.MyRegistrationsView.as_view(), name="registrations"),
    path("registrations/quote", views.QuoteView.as_view(), name="registration-quote"),
    path(
        "registrations/<int:registration_id>",
        views.MyRegistrationView.as_view(),
        name="registration",
    ),
    path(
        "registrations/<int:registration_id>/cancel",
        views.MyRegistrationCancelView.as_view(),
        name="registration-cancel",
    ),
    path(
        "registrations/<int:registration_id>/proof",
        views.MyRegistrationProofView.as_view(),
        name="registration-proof",
    ),
    path(
        "registrations/<int:registration_id>/qr",
        views.MyRegistrationQrView.as_view(),
        name="registration-qr",
    ),
]
