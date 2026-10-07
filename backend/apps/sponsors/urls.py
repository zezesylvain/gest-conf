"""Routes des partenaires (plan L8 §4, N5)."""

from django.urls import path

from apps.sponsors import views

app_name = "sponsors"

E = "manage/editions/<int:edition_id>"
SPONSORS = views.SponsorViewSet
S = f"{E}/sponsors/<int:sponsor_id>"
LEVELS = views.SponsorLevelViewSet

urlpatterns = [
    path(
        f"{E}/sponsors",
        SPONSORS.as_view({"get": "overview", "post": "create"}),
        name="manage-sponsors",
    ),
    path(
        f"{E}/sponsors/export", SPONSORS.as_view({"get": "export"}), name="manage-sponsors-export"
    ),
    path(
        S,
        SPONSORS.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="manage-sponsor",
    ),
    path(
        f"{S}/logo",
        views.SponsorLogoViewSet.as_view({"get": "content", "put": "upload", "delete": "remove"}),
        name="manage-sponsor-logo",
    ),
    path(
        f"{S}/benefits", SPONSORS.as_view({"post": "add_benefit"}), name="manage-sponsor-benefits"
    ),
    path(
        f"{S}/benefits/<int:benefit_id>",
        SPONSORS.as_view({"patch": "update_benefit", "delete": "remove_benefit"}),
        name="manage-sponsor-benefit",
    ),
    path(
        f"{E}/sponsor-levels",
        LEVELS.as_view({"get": "list", "post": "create"}),
        name="manage-sponsor-levels",
    ),
    path(
        f"{E}/sponsor-levels/<int:level_id>",
        LEVELS.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-sponsor-level",
    ),
    path("public/sponsors", views.PublicSponsorsView.as_view(), name="public-sponsors"),
]
