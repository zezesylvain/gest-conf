"""Routes de l'API.

L'application est montée sous /api (voir config/mount.py) : les chemins
ci-dessous sont relatifs à ce préfixe. « v1/health » répond donc à /api/v1/health.
Aucune route d'administration Django (règle n° 1 de CLAUDE.md).
"""

from django.conf import settings
from django.urls import include, path

from apps.core.views import not_found

# Routes d'allauth montées sans condition mais non configurées (téléphone) : sans
# adaptateur de téléphone, elles lèvent NotImplementedError (erreur 500, vérifié).
# Déclarées avant l'inclusion d'allauth, elles répondent 404 JSON (plan L1 §9.2).
DISABLED_ALLAUTH_ROUTES = (
    "account/phone",
    "auth/phone/verify",
    "auth/phone/verify/resend",
)

urlpatterns = [
    path("v1/", include("apps.core.urls")),
    path("v1/", include("apps.accounts.urls")),
    path("v1/", include("apps.conferences.urls")),
    path("v1/", include("apps.portal.urls")),
    path("v1/", include("apps.submissions.urls")),
    path("v1/", include("apps.communications.urls")),
    path("v1/", include("apps.reviews.urls")),
    path("v1/", include("apps.program.urls")),
    path("v1/", include("apps.registrations.urls")),
    path("v1/", include("apps.payments.urls")),
    path("v1/", include("apps.events.urls")),
    # Authentification : vues d'allauth en mode headless, client « browser » seul
    # (/api/_allauth/browser/v1/…, décision D4). Hors du schéma OpenAPI.
    *(path(f"_allauth/browser/v1/{route}", not_found) for route in DISABLED_ALLAUTH_ROUTES),
    path("_allauth/", include("allauth.headless.urls")),
]

if settings.DEBUG:
    # Schéma OpenAPI publié uniquement en développement (étude §9.1).
    from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

    urlpatterns += [
        path("v1/schema", SpectacularAPIView.as_view(), name="schema"),
        path("v1/docs", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    ]

handler400 = "apps.core.views.bad_request"
handler403 = "apps.core.views.permission_denied"
handler404 = "apps.core.views.not_found"
handler500 = "apps.core.views.server_error"
