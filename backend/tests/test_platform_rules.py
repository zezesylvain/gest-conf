"""Garde-fous automatisés sur les règles non négociables de CLAUDE.md."""

from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts.models import User


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
