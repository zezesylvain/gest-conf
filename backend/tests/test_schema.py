"""Schéma OpenAPI : noms d'énumérations stables et composant ApiError (plan L1 §3.1, §9.5)."""

import pytest
from django.conf import settings
from django.test import override_settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.generators import SchemaGenerator

from apps.core.authentication import SessionAuthentication
from apps.core.errors import ErrorCode
from apps.core.schema import SessionScheme

# Composants ajoutés par drf-spectacular pour les choix vides ou nuls.
SPECTACULAR_HELPER_ENUMS = {"BlankEnum", "NullEnum"}


def generate_schema(urlconf: str | None = None) -> dict:
    return SchemaGenerator(urlconf=urlconf).get_schema(request=None, public=True)


@pytest.fixture(scope="module")
def schema() -> dict:
    return generate_schema()


def test_every_schema_enum_has_explicit_name(schema):
    """Méta-test : toute énumération du schéma porte un nom déclaré dans ENUM_NAME_OVERRIDES.

    Sans surcharge, drf-spectacular peut renommer une énumération sans avertissement
    (StatusEnum → HealthStatusEnum dès qu'un second champ « status » apparaît), ce qui
    fait disparaître le type du client TypeScript généré.
    """
    enum_components = {
        name for name, component in schema["components"]["schemas"].items() if "enum" in component
    }
    declared = set(settings.SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"])
    assert enum_components - SPECTACULAR_HELPER_ENUMS <= declared
    # Réciproque : pas de surcharge orpheline (jeu de choix disparu ou mal référencé).
    assert declared <= enum_components


def test_health_enums(schema):
    components = schema["components"]["schemas"]
    health = components["Health"]["properties"]
    assert health["status"] == {"$ref": "#/components/schemas/HealthStatus"}
    assert health["database"] == {"$ref": "#/components/schemas/ServiceStatus"}
    assert health["cache"] == {"$ref": "#/components/schemas/ServiceStatus"}
    assert components["HealthStatus"]["enum"] == ["ok", "degraded"]
    assert components["ServiceStatus"]["enum"] == ["ok", "error"]


def test_api_error_component(schema):
    """ApiError est présent même si aucune opération ne le référence, avec code ∈ ErrorCode."""
    components = schema["components"]["schemas"]
    api_error = components["ApiError"]
    assert set(api_error["properties"]) == {"code", "message", "fields"}
    assert set(api_error["required"]) == {"code", "message", "fields"}
    assert api_error["properties"]["code"] == {"$ref": "#/components/schemas/ErrorCode"}
    assert components["ErrorCode"]["enum"] == ErrorCode.values


def test_schema_generation_is_repeatable():
    """Le crochet ApiError ne doit pas altérer l'état global (générations successives)."""
    assert generate_schema() == generate_schema()


def test_session_authentication_subclass_is_documented():
    """Notre SessionAuthentication est reconnue par drf-spectacular (pas d'avertissement)."""
    extension = OpenApiAuthenticationExtension.get_match(SessionAuthentication())
    assert isinstance(extension, SessionScheme)


@override_settings(ROOT_URLCONF="apps.core.tests.urls")
def test_session_security_scheme_in_schema():
    schema = generate_schema(urlconf="apps.core.tests.urls")
    assert schema["components"]["securitySchemes"]["cookieAuth"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": settings.SESSION_COOKIE_NAME,
    }


def test_schema_version_is_the_project_version(schema):
    """Plan L1 §9.5 : la version du schéma est celle du projet (pyproject.toml, source unique)."""
    import tomllib

    with (settings.BASE_DIR / "pyproject.toml").open("rb") as handle:
        project_version = tomllib.load(handle)["project"]["version"]
    assert settings.SPECTACULAR_SETTINGS["VERSION"] == project_version
    assert schema["info"]["version"] == project_version
