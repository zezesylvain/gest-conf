"""Assainissement du HTML des sections (E3, plan L2 §6).

Liste blanche, par ``html.parser`` de la bibliothèque standard (pas de dépendance binaire,
règle n° 10). Le portail réassainit au rendu avec la même liste (défense en profondeur) :
toute modification ici se reporte dans ``portail/.../sanitize.ts``.

- balises gardées : ``ALLOWED_TAGS`` (``b`` et ``i`` deviennent ``strong`` et ``em``) ;
- balises dangereuses supprimées **avec leur contenu** : ``DROPPED_WITH_CONTENT`` ;
- autres balises retirées, leur texte conservé ;
- aucun attribut, sauf ``href`` sur ``a`` : ``http(s):``, ``mailto:``, ``tel:`` ou chemin
  interne (``/…``, jamais ``//…``) ;
- commentaires, déclarations et instructions supprimés ; balises fermées en fin de texte.

La sortie est stable : ``sanitize_html(sanitize_html(x)) == sanitize_html(x)``.
"""

from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset(
    {"p", "br", "strong", "em", "ul", "ol", "li", "a", "h3", "h4", "blockquote"}
)
RENAMED_TAGS = {"b": "strong", "i": "em"}
VOID_TAGS = frozenset({"br"})
IMPLICITLY_CLOSED = frozenset({"li", "p"})
DROPPED_WITH_CONTENT = frozenset(
    {
        "script",
        "style",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "template",
        "noscript",
        "textarea",
        "select",
        "title",
        "head",
    }
)
ALLOWED_SCHEMES = ("http:", "https:", "mailto:", "tel:")
MAX_LENGTH = 20_000

_CONTROL = re.compile(r"[\x00-\x20\x7f]+")


def safe_href(value: str) -> str | None:
    """Lien accepté, normalisé, ou ``None``. Les blancs et caractères de contrôle sont
    retirés avant l'examen du schéma (``java\\tscript:`` est refusé)."""
    href = _CONTROL.sub("", value or "")
    if not href:
        return None
    lowered = href.lower()
    if lowered.startswith("/"):
        return href if not lowered.startswith("//") and "\\" not in href else None
    if lowered.startswith(ALLOWED_SCHEMES):
        return href
    return None


class _Sanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[str] = []
        self.dropping = 0  # profondeur dans une balise supprimée avec son contenu

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.dropping += 1
            return
        if self.dropping:
            return
        tag = RENAMED_TAGS.get(tag, tag)
        if tag not in ALLOWED_TAGS:
            return
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}>")
            return
        if tag in IMPLICITLY_CLOSED and self.stack and self.stack[-1] == tag:
            # « <li>un<li>deux » : le second <li> ferme le premier, comme dans un navigateur.
            self.out.append(f"</{self.stack.pop()}>")
        attributes = ""
        if tag == "a":
            href = next((safe_href(value or "") for name, value in attrs if name == "href"), None)
            if href:
                attributes = f' href="{escape(href, quote=True)}"'
        self.out.append(f"<{tag}{attributes}>")
        self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in DROPPED_WITH_CONTENT or self.dropping:
            return
        tag = RENAMED_TAGS.get(tag, tag)
        if tag in VOID_TAGS:
            self.out.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in DROPPED_WITH_CONTENT:
            self.dropping = max(0, self.dropping - 1)
            return
        if self.dropping:
            return
        tag = RENAMED_TAGS.get(tag, tag)
        if tag not in self.stack:
            return  # fermeture orpheline ignorée
        # Ferme les balises restées ouvertes à l'intérieur.
        while self.stack:
            current = self.stack.pop()
            self.out.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.dropping:
            self.out.append(escape(data, quote=False))

    def result(self) -> str:
        self.close()
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")
        return "".join(self.out).strip()


def sanitize_html(value: str) -> str:
    """HTML réduit à la liste blanche. Texte brut accepté (échappé)."""
    if not value:
        return ""
    parser = _Sanitizer()
    parser.feed(value)
    return parser.result()
