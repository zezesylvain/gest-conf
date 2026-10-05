"""Garde-fous automatisés sur les règles non négociables de CLAUDE.md."""

import ast
from pathlib import Path

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.db.models import UniqueConstraint
from django.urls import URLResolver, get_resolver
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.permissions import CsrfEnforced


def test_django_admin_is_not_installed():
    """Règle n° 1 : pas d'admin Django."""
    assert "django.contrib.admin" not in settings.INSTALLED_APPS


def test_no_admin_module_in_project_apps():
    """Règle n° 1 : aucun fichier admin.py dans les applications."""
    apps_dir = Path(settings.BASE_DIR) / "apps"
    assert list(apps_dir.rglob("admin.py")) == []


@pytest.mark.django_db
def test_admin_url_is_not_routed(client):
    response = client.get("/admin/")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_user_has_no_global_role_flag():
    """Règle n° 5 : pas de rôle global implicite (is_superuser, is_staff)."""
    field_names = {field.name for field in User._meta.get_fields()}
    assert not {"is_superuser", "is_staff"} & field_names


def test_primary_keys_are_bigint():
    """Étude §8.2 : identifiants BIGINT."""
    assert settings.DEFAULT_AUTO_FIELD == "django.db.models.BigAutoField"


def test_api_renders_json_only():
    """Pas d'API navigable (gabarits HTML) : JSON uniquement."""
    assert settings.REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] == [
        "rest_framework.renderers.JSONRenderer"
    ]


def test_api_requires_authentication_by_default():
    """Règle n° 2 : tout endpoint est fermé sauf ouverture explicite."""
    assert settings.REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] == [
        "rest_framework.permissions.IsAuthenticated"
    ]


# --- Méta-tests sur le code source des applications (plan L1 §3.1, §3.3, §5.3) ------

APPS_DIR = Path(settings.BASE_DIR) / "apps"


def _python_sources() -> list[tuple[Path, ast.Module]]:
    """Arbres syntaxiques de tous les fichiers Python de apps/, migrations comprises."""
    return [(path, ast.parse(path.read_text(), str(path))) for path in APPS_DIR.rglob("*.py")]


def _called_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else ""


def test_no_conditional_unique_constraint_in_sources():
    """Pas d'UniqueConstraint(condition=…) : MariaDB ne la crée pas (W036), alors que
    SQLite l'applique, et les tests locaux passeraient à tort (plan L1 §3.1).
    Utiliser la « clé d'unicité nullable »."""
    offenders = [
        f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
        for path, tree in _python_sources()
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _called_name(node) == "UniqueConstraint"
        and any(keyword.arg == "condition" for keyword in node.keywords)
    ]
    assert offenders == []


def test_no_conditional_unique_constraint_in_models():
    """Modèles du projet seulement : allauth, par exemple, en déclare une (L1.3, §12.3)."""
    offenders = [
        f"{model._meta.label}.{constraint.name}"
        for model in django_apps.get_models()
        if model._meta.app_config.name.startswith("apps.")
        for constraint in model._meta.constraints
        if isinstance(constraint, UniqueConstraint) and constraint.condition is not None
    ]
    assert offenders == []


FORBIDDEN_PERMISSION_NAMES = {
    "DjangoModelPermissions",
    "DjangoModelPermissionsOrAnonReadOnly",
    "DjangoObjectPermissions",
    "has_perm",
    "has_perms",
    "has_module_perms",
}


def test_no_django_model_permissions_nor_has_perm():
    """Règle n° 5 : droits rattachés à une édition (UserRole), jamais les permissions
    globales de Django ; User n'a d'ailleurs pas PermissionsMixin (plan L1 §3.3)."""
    offenders = []
    for path, tree in _python_sources():
        for node in ast.walk(tree):
            name = (
                node.attr
                if isinstance(node, ast.Attribute)
                else node.id
                if isinstance(node, ast.Name)
                else node.name
                if isinstance(node, ast.alias | ast.FunctionDef)
                else None
            )
            if name is not None and name.split(".")[-1] in FORBIDDEN_PERMISSION_NAMES:
                offenders.append(f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}: {name}")
    assert offenders == []


def test_no_all_fields_shortcut():
    """Champs, filtres et tris toujours explicites : jamais « "__all__" » (plan L1 §5.3).
    Un tri ou un filtre sur un champ caché servirait d'oracle contre le double aveugle."""
    offenders = [
        f"{path.relative_to(settings.BASE_DIR)}:{node.lineno}"
        for path, tree in _python_sources()
        if "migrations" not in path.parts
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value == "__all__"
    ]
    assert offenders == []


# --- CSRF des vues publiques (plan L1 §4.6, cas 3) ------------------------------------

UNSAFE_METHODS = {"post", "put", "patch", "delete"}

# Vues publiques acceptant (en apparence) une méthode non sûre sans CsrfEnforced, avec la
# justification de l'exception. Toute nouvelle entrée se justifie en revue.
CSRF_EXEMPTIONS = {
    # Vue Django simple (csrf_exempt) : GET seul ; toute autre méthode reçoit 404
    # (désactivée) ou 405, sans aucun effet.
    "apps.core.views.request_diagnostics": "GET seul, sans effet",
}


def _iter_callbacks(patterns, prefix=""):
    """(route, vue) de toutes les URL résolues, includes compris."""
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            yield from _iter_callbacks(pattern.url_patterns, prefix + str(pattern.pattern))
        else:
            yield prefix + str(pattern.pattern), pattern.callback


def _requires_authentication(permission_classes) -> bool:
    return any(
        isinstance(permission, type) and issubclass(permission, IsAuthenticated)
        for permission in permission_classes
    )


def views_without_csrf_on_unsafe_methods(urlconf: str) -> list[str]:
    """Vues qu'un visiteur anonyme peut appeler en POST/PUT/PATCH/DELETE sans contrôle CSRF.

    DRF ne contrôle le CSRF que pour une session authentifiée
    (``SessionAuthentication.authenticate`` renvoie ``None`` sans appeler
    ``enforce_csrf`` pour un anonyme) : une vue DRF ouverte aux anonymes (sans
    ``IsAuthenticated``) qui expose une méthode non sûre doit porter ``CsrfEnforced``.
    Une vue Django ``csrf_exempt`` échappe aussi au middleware CSRF.
    """
    offenders = []
    for route, callback in _iter_callbacks(get_resolver(urlconf).url_patterns):
        name = f"{callback.__module__}.{callback.__qualname__}"
        view_class = getattr(callback, "cls", None)
        if isinstance(view_class, type) and issubclass(view_class, APIView):
            name = f"{view_class.__module__}.{view_class.__qualname__}"
            actions = getattr(callback, "actions", None)  # ViewSet : méthodes routées
            methods = (
                set(actions) if actions else {m for m in UNSAFE_METHODS if hasattr(view_class, m)}
            )
            permissions = view_class.permission_classes
            if (
                methods & UNSAFE_METHODS
                and CsrfEnforced not in permissions
                and not _requires_authentication(permissions)
                and name not in CSRF_EXEMPTIONS
            ):
                offenders.append(f"{route} ({name})")
        elif getattr(callback, "csrf_exempt", False) and name not in CSRF_EXEMPTIONS:
            offenders.append(f"{route} ({name}, csrf_exempt)")
    return offenders


def test_public_unsafe_views_enforce_csrf():
    """Plan L1 §4.6, cas 3 : toute vue publique qui accepte une méthode non sûre porte
    ``CsrfEnforced`` (ou figure, justifiée, dans ``CSRF_EXEMPTIONS``)."""
    assert views_without_csrf_on_unsafe_methods(settings.ROOT_URLCONF) == []


def test_csrf_meta_test_detects_unprotected_views():
    """Le détecteur signale bien les vues publiques sans CsrfEnforced des vues de test,
    et ignore celles qui sont protégées (CsrfEnforced, IsAuthenticated) ou en GET seul."""
    offenders = "\n".join(views_without_csrf_on_unsafe_methods("apps.core.tests.urls"))
    assert "EchoView" in offenders
    assert "FieldValidationView" in offenders
    assert "CsrfEnforcedView" not in offenders
    assert "ProtectedView" not in offenders
    assert "ScopedThrottleView" not in offenders
    assert "csrf_protected_django_view" not in offenders


# --- Rôles par édition et vues ouvertes (plan L1 §5.3, §5.9) ------------------------------

# Vues DRF accessibles sans authentification, avec la justification. Toute nouvelle entrée
# se justifie en revue (règle n° 2).
ANONYMOUS_VIEWS = {
    "apps.core.views.HealthView": "supervision et test de fumée",
    "apps.accounts.manage_views.InvitationLookupView": "jeton d'invitation (lecture)",
    "apps.accounts.manage_views.InvitationDeclineView": "jeton d'invitation (refus)",
    "apps.conferences.views.PublicCurrentEditionView": "portail public",
    # Lot L2 : contenus du portail, lus au build (pré-rendu) et dans le navigateur.
    "apps.portal.views.PublicRoutesView": "portail public (routes à pré-rendre)",
    "apps.portal.views.PublicCompositionView": "portail public (composition d'une page)",
    "apps.portal.views.PublicMenuView": "portail public (menus)",
    "apps.portal.views.PublicSiteView": "portail public (données des gabarits)",
}

# Seule vue de ``v1/manage/`` hors ``ManageViewSet`` : sélecteur d'édition.
MANAGE_EXCEPTIONS = {"apps.conferences.views.ManageEditionListView"}


def _drf_routes():
    for route, callback in _iter_callbacks(get_resolver(settings.ROOT_URLCONF).url_patterns):
        view_class = getattr(callback, "cls", None)
        if isinstance(view_class, type) and issubclass(view_class, APIView):
            yield route, view_class, f"{view_class.__module__}.{view_class.__qualname__}"


def test_anonymous_views_are_whitelisted():
    """Règle n° 2 : toute vue DRF sans ``IsAuthenticated`` figure dans la liste blanche."""
    opened = {
        name
        for _route, view_class, name in _drf_routes()
        if not _requires_authentication(view_class.permission_classes)
    }
    assert opened == set(ANONYMOUS_VIEWS)


def test_every_edition_route_inherits_manage_viewset():
    """§5.3 : toute route de ``v1/manage/`` charge l'édition, vérifie la capacité et la 2FA."""
    from apps.accounts.permissions import ManageViewSet

    manage_routes = [
        (route, view_class, name)
        for route, view_class, name in _drf_routes()
        if route.startswith("v1/manage/")
    ]
    assert manage_routes
    for route, view_class, name in manage_routes:
        if name in MANAGE_EXCEPTIONS:
            continue
        assert issubclass(view_class, ManageViewSet), route
        assert route.startswith("v1/manage/editions/<int:edition_id>"), route


def test_headless_browser_client_only_and_reauthentication():
    """D4, §4.5 : client ``browser`` seul (pas de jeton applicatif), réauthentification
    exigée pour les opérations sensibles."""
    assert tuple(settings.HEADLESS_CLIENTS) == ("browser",)
    assert settings.ACCOUNT_REAUTHENTICATION_REQUIRED is True
