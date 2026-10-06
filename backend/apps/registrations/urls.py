"""Routes des inscriptions (plan L6 §4)."""

from django.urls import path

from apps.registrations import views

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
    path("public/registration", views.PublicRegistrationView.as_view(), name="public-registration"),
    path("registrations/quote", views.QuoteView.as_view(), name="registration-quote"),
]
