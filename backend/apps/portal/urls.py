"""Routes du CMS du portail (plan L2 §4)."""

from django.urls import path

from apps.portal import views

app_name = "portal"

E = "manage/editions/<int:edition_id>/portal"


def _crud(prefix: str, viewset, name: str) -> list:
    return [
        path(
            f"{E}/{prefix}",
            viewset.as_view({"get": "list", "post": "create"}),
            name=f"manage-portal-{name}-list",
        ),
        path(
            f"{E}/{prefix}/<int:item_id>",
            viewset.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
            name=f"manage-portal-{name}-detail",
        ),
    ]


urlpatterns = [
    # Routes d'action déclarées avant les détails (« preview », « reorder » ne sont pas des id).
    path(
        f"{E}/sections/preview",
        views.SectionViewSet.as_view({"post": "preview"}),
        name="manage-portal-sections-preview",
    ),
    *_crud("sections", views.SectionViewSet, "sections"),
    *_crud("pages", views.PageViewSet, "pages"),
    *(
        path(
            f"{E}/pages/<int:item_id>/{name}",
            views.PageViewSet.as_view({"post": name}),
            name=f"manage-portal-pages-{name}",
        )
        for name in ("attach", "detach", "reorder")
    ),
    path(
        f"{E}/menu/reorder",
        views.MenuItemViewSet.as_view({"post": "reorder"}),
        name="manage-portal-menu-reorder",
    ),
    *_crud("menu", views.MenuItemViewSet, "menu"),
    *_crud("files", views.PublicFileViewSet, "files"),
    path(
        f"{E}/files/<int:item_id>/content",
        views.PublicFileViewSet.as_view({"get": "content"}),
        name="manage-portal-files-content",
    ),
    path(
        f"{E}/poster",
        views.PosterViewSet.as_view({"get": "retrieve", "put": "update"}),
        name="manage-portal-poster",
    ),
    path(
        f"{E}/status",
        views.PublicationStatusViewSet.as_view({"get": "retrieve"}),
        name="manage-portal-status",
    ),
    path("public/portal/routes", views.PublicRoutesView.as_view(), name="public-portal-routes"),
    path(
        "public/portal/pages/<slug:slug>",
        views.PublicCompositionView.as_view(),
        name="public-portal-page",
    ),
    path("public/portal/menu", views.PublicMenuView.as_view(), name="public-portal-menu"),
    path("public/portal/site", views.PublicSiteView.as_view(), name="public-portal-site"),
    path(
        "public/files/<uuid:uuid>/<str:name>",
        views.PublicFileView.as_view(),
        name="public-file",
    ),
]
