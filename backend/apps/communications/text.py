"""Version texte d'un HTML assaini (plan L8, bilan de L8.0 : précision de N11).

``strip_tags`` perd la cible des liens et colle les éléments de liste : ce petit
convertisseur suit la liste blanche de l'assainisseur de L2 (``apps/portal/sanitizer.py``)
et rend les paragraphes séparés d'une ligne vide, les puces « - » (numéros pour une liste
ordonnée), les citations préfixées par « > » et les liens « texte (adresse) ». Un chemin
interne (``/fr/…``) devient une adresse absolue : un e-mail n'a pas d'adresse de base.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

_SPACES = re.compile(r"[ \t\r\f\v]+")
_HEADINGS = frozenset({"p", "h3", "h4"})


def absolute_href(href: str, base_url: str) -> str:
    """Chemin interne (``/…``, jamais ``//…``) rendu absolu ; autre adresse inchangée."""
    if href.startswith("/") and not href.startswith("//"):
        return f"{base_url.rstrip('/')}{href}"
    return href


class _TextWriter(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        # (texte, liste de premier niveau de l'élément, None hors liste)
        self.blocks: list[tuple[str, int | None]] = []
        self.parts: list[str] = []
        self.lists: list[list] = []  # pile de [balise, compteur, numéro de la liste]
        self.list_count = 0
        self.links: list[tuple[str, int]] = []  # pile de (adresse, début du texte du lien)
        self.quote = 0
        self.item_prefix = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _HEADINGS:
            self._flush()
        elif tag == "blockquote":
            self._flush()
            self.quote += 1
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_count += 1
            self.lists.append([tag, 0, self.list_count])
        elif tag == "li":
            self._flush()
            if self.lists:
                self.lists[-1][1] += 1
                kind, counter, _number = self.lists[-1]
                self.item_prefix = f"{counter}. " if kind == "ol" else "- "
            else:
                self.item_prefix = "- "
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self.links.append((absolute_href(href, self.base_url), len(self.parts)))

    def handle_endtag(self, tag: str) -> None:
        if tag in _HEADINGS or tag == "li":
            self._flush()
        elif tag == "blockquote":
            self._flush()
            self.quote = max(0, self.quote - 1)
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
        elif tag == "a" and self.links:
            href, start = self.links.pop()
            label = " ".join("".join(self.parts[start:]).split())
            if href and href != label:
                self.parts.append(f" ({href})")

    def handle_data(self, data: str) -> None:
        self.parts.append(_SPACES.sub(" ", data.replace("\n", " ")))

    def _flush(self) -> None:
        text = "".join(self.parts)
        self.parts = []
        lines = [" ".join(line.split()) for line in text.split("\n")]
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()
        prefix, self.item_prefix = self.item_prefix, ""
        if not lines:
            return
        group = self.lists[0][2] if (prefix and self.lists) else None
        if prefix:
            indent = "  " * max(0, len(self.lists) - 1)
            lines = [f"{indent}{prefix}{lines[0]}"] + [
                f"{indent}{' ' * len(prefix)}{line}" for line in lines[1:]
            ]
        if self.quote:
            lines = [f"{'> ' * self.quote}{line}".rstrip() for line in lines]
        self.blocks.append(("\n".join(lines), group))

    def result(self) -> str:
        self._flush()
        out: list[str] = []
        previous: int | None = None
        for text, group in self.blocks:
            if out:
                # Les éléments d'une même liste se suivent sans ligne vide.
                out.append("\n" if (group is not None and group == previous) else "\n\n")
            out.append(text)
            previous = group
        return "".join(out)


def html_to_text(html: str, *, base_url: str = "") -> str:
    """Texte brut d'un HTML **déjà assaini** (liste blanche de L2)."""
    writer = _TextWriter(base_url)
    writer.feed(html or "")
    writer.close()
    return writer.result()
