"""Pages du site (plan L2 §2.2, compétence ``gestion-cms-portail-angular``).

``SITE_PAGES`` est la **liste unique** lue par le *seed*, la résolution des adresses, le
menu et les routes à pré-rendre. Une page du site a un gabarit codé dans le portail et une
adresse figée ; ses sections s'affichent après ce contenu. Les pages personnalisées vivent
sous ``/<langue>/p/<slug>/`` et n'ont que leurs sections.

Aucun import Django : données pures, réutilisées par la migration de données.
"""

from __future__ import annotations

from dataclasses import dataclass

LANGUAGES = ("fr", "en")
CUSTOM_PREFIX = "p"


@dataclass(frozen=True, slots=True)
class SitePage:
    slug: str
    path_fr: str
    path_en: str
    title_fr: str
    title_en: str
    # Page « à venir » (E6) : données en L5 et L6, sections éditables dès L2. Le programme
    # est servi depuis L5 (I7), l'inscription depuis L6 (J13), les intervenants, les
    # partenaires et les actualités depuis L8 (N5, N6, N10) : plus aucune page à venir.
    coming_soon: bool = False


SITE_PAGES: tuple[SitePage, ...] = (
    SitePage("home", "", "", "Accueil", "Home"),
    SitePage("call", "appel", "call", "Appel à communications", "Call for papers"),
    SitePage("dates", "dates", "dates", "Dates importantes", "Important dates"),
    SitePage("tracks", "thematiques", "tracks", "Thématiques", "Tracks"),
    SitePage("committees", "comites", "committees", "Comités", "Committees"),
    SitePage("program", "programme", "program", "Programme", "Programme"),
    SitePage("speakers", "intervenants", "speakers", "Intervenants", "Speakers"),
    SitePage("registration", "inscription", "registration", "Inscription", "Registration"),
    SitePage("sponsors", "partenaires", "partners", "Partenaires", "Partners"),
    SitePage("news", "actualites", "news", "Actualités", "News"),
)
SITE_ROUTES: dict[str, SitePage] = {page.slug: page for page in SITE_PAGES}


def site_page_path(page: SitePage, language: str) -> str:
    """Adresse publique, avec barre finale (adresse canonique servie par Apache)."""
    segment = page.path_fr if language == "fr" else page.path_en
    return f"/{language}/{segment}/" if segment else f"/{language}/"


def custom_page_path(slug: str, language: str) -> str:
    return f"/{language}/{CUSTOM_PREFIX}/{slug}/"


def page_paths(slug: str, *, is_system: bool) -> dict[str, str]:
    if is_system:
        page = SITE_ROUTES[slug]
        return {language: site_page_path(page, language) for language in LANGUAGES}
    return {language: custom_page_path(slug, language) for language in LANGUAGES}


# Sections « données » livrées par le seed : prêtes à poser, posées nulle part (le CMS
# ajoute, il ne remplace pas). (code, type, titre FR, titre EN, config)
SEED_SECTIONS: tuple[tuple[str, str, str, str, dict], ...] = (
    ("hero", "edition_hero", "", "", {"countdown": True}),
    ("key-dates", "key_dates", "Dates importantes", "Important dates", {}),
    ("tracks", "tracks", "Thématiques", "Tracks", {}),
    (
        "submission-types",
        "submission_types",
        "Formats de communication",
        "Presentation formats",
        {},
    ),
    ("documents", "documents", "Documents", "Documents", {}),
    (
        "committee-scientific",
        "committee",
        "Comité scientifique",
        "Scientific committee",
        {"committee": "scientific"},
    ),
    (
        "committee-organizing",
        "committee",
        "Comité d'organisation",
        "Organising committee",
        {"committee": "organizing"},
    ),
)

# Menu d'en-tête livré par le seed : pages du site, dans cet ordre.
SEED_HEADER_MENU: tuple[str, ...] = (
    "call",
    "dates",
    "tracks",
    "committees",
    "program",
    "speakers",
    "registration",
    "sponsors",
    "news",
)
