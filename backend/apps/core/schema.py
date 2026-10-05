"""Extensions du schéma OpenAPI (drf-spectacular), plan L1 §9.5.

- ``SessionScheme`` : l'extension fournie par drf-spectacular ne vise que la
  classe exacte de DRF (``match_subclasses = False``) ; sans celle-ci, chaque vue
  authentifiée par notre sous-classe produirait l'avertissement « could not
  resolve authenticator », donc un échec de ``spectacular --fail-on-warn``.
- ``add_api_error_component`` : ajoute le composant ``ApiError`` au schéma, même
  si aucune opération ne le référence, pour que le client TypeScript généré
  dispose du type et de l'union des codes (``ErrorCode``). Ce crochet doit
  précéder ``postprocess_schema_enums``, qui extrait l'énumération du champ ``code``
  et la nomme d'après ``ENUM_NAME_OVERRIDES``.
"""

from typing import Any

from drf_spectacular.authentication import SessionScheme as SpectacularSessionScheme
from drf_spectacular.plumbing import build_mocked_view
from drf_spectacular.settings import spectacular_settings
from drf_spectacular.utils import extend_schema

from apps.core.serializers import ApiErrorSerializer

API_ERROR_COMPONENT = "ApiError"


class SessionScheme(SpectacularSessionScheme):
    """Enregistrée à sa définition (``__init_subclass__``) : ce module est importé
    par ``CoreConfig.ready()``, avant toute génération du schéma."""

    target_class = "apps.core.authentication.SessionAuthentication"


def add_api_error_component(
    result: dict[str, Any], generator: Any, **kwargs: Any
) -> dict[str, Any]:
    """Crochet de post-traitement : enregistre ``ApiError`` dans le registre des composants.

    Le sérialiseur est résolu par l'``AutoSchema`` d'une vue fictive, comme le
    fait drf-spectacular pour les webhooks (``plumbing.build_mocked_view``).
    """
    view = build_mocked_view(
        method="GET",
        path="/",
        extend_schema_decorator=extend_schema(responses=ApiErrorSerializer),
        registry=generator.registry,
    )
    view.schema.resolve_serializer(ApiErrorSerializer, "response")
    result["components"] = generator.registry.build(spectacular_settings.APPEND_COMPONENTS)
    return result
