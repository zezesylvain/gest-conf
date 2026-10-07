"""Négociation de contenu de l'API (plan L8, bilan de L8.10).

L'API ne rend que du JSON (``DEFAULT_RENDERER_CLASSES``). Les vues qui servent un fichier
(exports CSV, XLSX et PDF, badges, iCal, images) renvoient une ``HttpResponse`` toute faite,
sans passer par un rendu ; mais DRF négocie le format **avant** d'exécuter la vue. Le client
généré annonce le type du fichier attendu (``Accept: text/csv``, ``application/pdf``,
``application/octet-stream``…) : aucune correspondance avec le JSON, donc un 406 avant même
la vue, et l'export échoue dans le navigateur.

Repli : quand le client n'accepte **que** des types de fichier, le rendu JSON est retenu ;
la vue sert son fichier, et une erreur (403, réauthentification, 400…) part dans le format
normalisé ``{code, message, fields}``, en JSON. RFC 9110, §12.5.1 : un serveur peut ignorer
l'en-tête ``Accept`` plutôt que répondre 406. Tout autre type non servi (``application/xml``)
reste refusé par un 406.
"""

from __future__ import annotations

from rest_framework.exceptions import NotAcceptable
from rest_framework.negotiation import DefaultContentNegotiation

# Types de fichier servis par l'API (schéma OpenAPI : réponses binaires), en liste fermée.
FILE_MEDIA_TYPES = frozenset(
    {
        "application/octet-stream",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "text/calendar",
        "text/csv",
    }
)
FILE_MAIN_TYPES = frozenset({"image"})


def is_file_media_type(token: str) -> bool:
    """``text/csv`` ou ``image/png;q=0.9`` : un type de fichier servi par l'API."""
    media_type = token.split(";", 1)[0].strip().lower()
    return media_type in FILE_MEDIA_TYPES or media_type.split("/", 1)[0] in FILE_MAIN_TYPES


class FileAwareContentNegotiation(DefaultContentNegotiation):
    """Négociation par défaut, avec repli sur le JSON pour une requête de fichier."""

    def select_renderer(self, request, renderers, format_suffix=None):
        try:
            return super().select_renderer(request, renderers, format_suffix)
        except NotAcceptable:
            accepts = [token for token in self.get_accept_list(request) if token]
            if accepts and all(is_file_media_type(token) for token in accepts):
                renderer = renderers[0]
                return renderer, renderer.media_type
            raise
