"""Textes des pièces (plan L7, K9, K12, K19) : gabarits par défaut et variables fermées.

Un gabarit ne connaît que les variables de sa nature, entre accolades (``{name}``) ; toute
autre accolade, attribut, indice, format ou conversion est refusé à l'enregistrement. Le
remplissage n'a donc rien d'un moteur de gabarit : ``str.format_map`` sur une liste
blanche de valeurs déjà calculées.
"""

from __future__ import annotations

import string
from collections.abc import Mapping

from django.utils.translation import gettext_lazy as _

from apps.events.models import DocumentNature as N

COMMON = ("name", "edition", "dates", "venue")
PLACEHOLDERS: Mapping[str, frozenset[str]] = {
    N.PARTICIPATION: frozenset(COMMON),
    N.PRESENTATION: frozenset((*COMMON, "title", "reference")),
    N.REVIEW: frozenset((*COMMON, "count")),
    N.LETTER: frozenset((*COMMON, "passport_name", "nationality", "passport", "stay", "embassy")),
}

TEXT_FIELDS = ("title_fr", "title_en", "body_fr", "body_en", "footer_fr", "footer_en")

DEFAULTS: Mapping[str, Mapping[str, str]] = {
    N.PARTICIPATION: {
        "title_fr": "Attestation de participation",
        "title_en": "Certificate of attendance",
        "body_fr": "Nous attestons que {name} a participé à {edition}, tenue {dates} à {venue}.",
        "body_en": "This is to certify that {name} attended {edition}, held {dates} in {venue}.",
        "footer_fr": "",
        "footer_en": "",
    },
    N.PRESENTATION: {
        "title_fr": "Attestation de communication",
        "title_en": "Certificate of presentation",
        "body_fr": (
            "Nous attestons que {name} a présenté la communication « {title} » ({reference}) "
            "à {edition}, tenue {dates} à {venue}."
        ),
        "body_en": (
            "This is to certify that {name} presented the paper “{title}” ({reference}) at "
            "{edition}, held {dates} in {venue}."
        ),
        "footer_fr": "",
        "footer_en": "",
    },
    N.REVIEW: {
        "title_fr": "Attestation d'évaluation",
        "title_en": "Certificate of reviewing",
        "body_fr": (
            "Nous attestons que {name} a évalué {count} soumission(s) pour le comité "
            "scientifique de {edition}."
        ),
        "body_en": (
            "This is to certify that {name} reviewed {count} submission(s) for the "
            "scientific committee of {edition}."
        ),
        "footer_fr": "",
        "footer_en": "",
    },
    N.LETTER: {
        "title_fr": "Lettre d'invitation",
        "title_en": "Letter of invitation",
        "body_fr": (
            "À l'attention de : {embassy}.\n\nNous avons le plaisir d'inviter "
            "{passport_name}, de nationalité {nationality}, titulaire du passeport n° "
            "{passport}, à participer à {edition}, qui se tiendra {dates} à {venue}. Séjour "
            "prévu : {stay}.\n\nCette lettre n'engage pas la prise en charge des frais de "
            "voyage ni de séjour."
        ),
        "body_en": (
            "To: {embassy}.\n\nWe are pleased to invite {passport_name}, a national of "
            "{nationality}, holder of passport no. {passport}, to attend {edition}, to be held "
            "{dates} in {venue}. Planned stay: {stay}.\n\nThis letter does not imply that "
            "travel or accommodation expenses will be covered."
        ),
        "footer_fr": "",
        "footer_en": "",
    },
}


def placeholder_errors(text: str, nature: str) -> list[str]:
    """Erreurs d'un texte de gabarit (vide : valide)."""
    allowed = PLACEHOLDERS[nature]
    try:
        parsed = list(string.Formatter().parse(text))
    except ValueError:
        return [str(_("Accolade non fermée : doublez-la ({{ ou }}) pour l'afficher."))]
    errors = []
    for _literal, field, spec, conversion in parsed:
        if field is None:
            continue
        if field not in allowed or spec or conversion:
            errors.append(
                str(_("Variable inconnue : {%(field)s}. Variables permises : %(allowed)s."))
                % {
                    "field": field,
                    "allowed": ", ".join(f"{{{name}}}" for name in sorted(allowed)),
                }
            )
    return errors


def fill(text: str, values: Mapping[str, str]) -> str:
    """Texte rempli ; une variable permise mais sans valeur reste vide."""

    class Values(dict):
        def __missing__(self, key):
            return ""

    return text.format_map(Values(values))
