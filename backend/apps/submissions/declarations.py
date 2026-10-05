"""Déclarations de l'auteur à la soumission (plan L3, F7).

Les textes (FR et EN) sont dans les traductions du portail, sous des clés dérivées du
code ; leur **version** est enregistrée avec chaque acceptation. Toute nouvelle version
d'un texte exige une nouvelle acceptation avant de soumettre ou de modifier. Les textes
« v0 » sont provisoires : les textes définitifs (Q14) bloquent l'ouverture réelle de
l'appel, pas le développement.
"""

from __future__ import annotations

DECLARATIONS: dict[str, str] = {
    "originality": "2026-10-v0",
    "ethics": "2026-10-v0",
    "conflicts": "2026-10-v0",
    "publication": "2026-10-v0",
}


def missing_declarations(declarations: dict) -> list[str]:
    """Codes non acceptés dans leur version courante."""
    missing = []
    for code, version in DECLARATIONS.items():
        entry = declarations.get(code) or {}
        if not (entry.get("accepted") is True and entry.get("text_version") == version):
            missing.append(code)
    return missing
