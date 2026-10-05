"""Logique du CMS du portail (plan L2 §2.2 ; compétence ``gestion-cms-portail-angular``).

Toute écriture passe par ces services : validation, assainissement du HTML (E3), refus sur
une édition archivée (409 ``edition_archived``), journal d'audit (``portal.*``, RG-17).
Les trois écritures de composition (poser, retirer, ordonner) renvoient la composition
**relue depuis la base**.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max, Prefetch, Q, QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.portal.models import (
    MenuItem,
    MenuLocation,
    Page,
    PageSection,
    Publication,
    Section,
    SectionType,
)
from apps.portal.sanitizer import MAX_LENGTH, safe_href, sanitize_html
from apps.portal.site import SEED_HEADER_MENU, SEED_SECTIONS, SITE_PAGES, SITE_ROUTES

SECTION_FIELDS = (
    "code",
    "section_type",
    "title_fr",
    "title_en",
    "subtitle_fr",
    "subtitle_en",
    "body_fr",
    "body_en",
    "cta_label_fr",
    "cta_label_en",
    "cta_url",
    "cta2_label_fr",
    "cta2_label_en",
    "cta2_url",
    "config",
    "published",
)
PAGE_FIELDS = ("slug", "title_fr", "title_en", "description_fr", "description_en", "published")
# Page du site : adresse figée, toujours publiée (gabarit codé dans le portail).
SYSTEM_PAGE_FIELDS = ("title_fr", "title_en", "description_fr", "description_en")
MENU_FIELDS = (
    "location",
    "label_fr",
    "label_en",
    "page",
    "url",
    "new_tab",
    "position",
    "published",
)

# Réglages permis par type : nom → (validateur, description pour le message).
LIMIT_MAX = 20


def _limit(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= LIMIT_MAX


SECTION_CONFIG: Mapping[str, Mapping[str, Any]] = {
    SectionType.RICH_TEXT: {},
    SectionType.CTA_BANNER: {},
    SectionType.IMAGE_TEXT: {"image_position": lambda v: v in ("left", "right")},
    SectionType.EDITION_HERO: {"countdown": lambda v: isinstance(v, bool)},
    SectionType.KEY_DATES: {"limit": _limit},
    SectionType.TRACKS: {},
    SectionType.SUBMISSION_TYPES: {},
    SectionType.DOCUMENTS: {"limit": _limit},
    SectionType.COMMITTEE: {"committee": lambda v: v in ("scientific", "organizing")},
}
REQUIRED_CONFIG: Mapping[str, tuple[str, ...]] = {SectionType.COMMITTEE: ("committee",)}

# Actions du journal qui changent ce qu'affiche le portail : comptées comme
# « modifications non publiées » depuis la dernière mise en ligne (E1).
PORTAL_AFFECTING_ACTIONS = (
    "portal.",
    "edition.updated",
    "edition.status_changed",
    "track.",
    "submission_type.",
    "key_date.",
)


# --- Outils ------------------------------------------------------------------------------

# Adresse e-mail dans un texte libre (corps, lien mailto:) : masquée dans le journal, qui
# refuse toute adresse en clair (plan L1 §7.2). « contact@conf.org » → « c***@conf.org ».
_EMAIL_LOCAL_PART = re.compile(r"[^\s@<>\"'(),;:/*]+@")


def _mask_emails(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_LOCAL_PART.sub(lambda match: f"{match.group(0)[0]}***@", value)
    if isinstance(value, dict):
        return {key: _mask_emails(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_mask_emails(item) for item in value]
    return value


def _values(instance) -> dict[str, Any]:
    """Valeurs brutes des ``AUDIT_FIELDS`` (clé étrangère : identifiant)."""
    result = {}
    for name in type(instance).AUDIT_FIELDS:
        field = instance._meta.get_field(name)
        attribute = field.attname if field.is_relation and field.many_to_one else name
        result[name] = getattr(instance, attribute)
    return result


def snapshot(instance) -> dict[str, Any]:
    """Cliché d'audit des contenus du portail : ``AUDIT_FIELDS``, adresses masquées."""
    return _mask_emails(_values(instance))


def _validation(exc: ValidationError) -> Invalid:
    if hasattr(exc, "error_dict"):
        return Invalid(fields=exc.message_dict)
    return Invalid(fields={"non_field_errors": exc.messages})


def _save(instance, *, unique_field: str) -> None:
    try:
        instance.full_clean(exclude=["edition"])
    except ValidationError as exc:
        raise _validation(exc) from exc
    try:
        with transaction.atomic():
            instance.save()
    except IntegrityError as exc:
        raise Invalid(fields={unique_field: [_("Cette valeur est déjà utilisée.")]}) from exc


def _apply(instance, data: Mapping[str, Any], allowed: Iterable[str]) -> list[str]:
    changed = []
    for name in allowed:
        if name in data and getattr(instance, name) != data[name]:
            setattr(instance, name, data[name])
            changed.append(name)
    return changed


def _diff(before: dict, instance, changed: list[str]) -> tuple[dict, dict]:
    """``before`` : valeurs brutes (``_values``) ; clichés masqués des champs changés."""
    after = _values(instance)
    keys = [name for name in changed if name in before]
    return (
        _mask_emails({k: before[k] for k in keys}),
        _mask_emails({k: after[k] for k in keys}),
    )


def _check_url(value: str, field: str) -> str:
    value = (value or "").strip()
    if value and safe_href(value) is None:
        raise Invalid(
            fields={field: [_("Adresse refusée : https:, mailto:, tel: ou chemin interne (/…).")]}
        )
    return value


# --- Sections ---------------------------------------------------------------------------


def _clean_section(section: Section) -> None:
    """Assainit le HTML, contrôle les liens et la configuration selon le type."""
    errors: dict[str, list] = {}
    for language in ("fr", "en"):
        name = f"body_{language}"
        raw = getattr(section, name) or ""
        if len(raw) > MAX_LENGTH:
            errors[name] = [
                _("Texte trop long (%(max)s caractères au plus).") % {"max": MAX_LENGTH}
            ]
        setattr(section, name, sanitize_html(raw))
    for field in ("cta_url", "cta2_url"):
        try:
            setattr(section, field, _check_url(getattr(section, field), field))
        except Invalid as exc:
            errors.update(exc.fields)
    config = section.config if isinstance(section.config, dict) else None
    allowed = SECTION_CONFIG.get(section.section_type)
    if config is None or allowed is None:
        errors["config"] = [_("Configuration invalide.")]
    else:
        unknown = sorted(set(config) - set(allowed))
        invalid = sorted(
            name for name, check in allowed.items() if name in config and not check(config[name])
        )
        missing = [
            name for name in REQUIRED_CONFIG.get(section.section_type, ()) if name not in config
        ]
        if unknown or invalid or missing:
            errors["config"] = [
                _("Configuration invalide : %(names)s.")
                % {"names": ", ".join(unknown + invalid + missing)}
            ]
    if section.is_data and (section.body_fr or section.body_en):
        errors["body_fr"] = [
            _("Une section de données n'a pas de corps : son contenu vient de l'édition.")
        ]
    if errors:
        raise Invalid(fields=errors)


@transaction.atomic
def create_section(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Section:
    ensure_editable(edition)
    section = Section(edition=edition)
    _apply(section, data, SECTION_FIELDS)
    _clean_section(section)
    _save(section, unique_field="code")
    record(
        "portal.section_created", actor=actor, edition=edition, obj=section, after=snapshot(section)
    )
    return section


@transaction.atomic
def update_section(section: Section, data: Mapping[str, Any], *, actor: Actor) -> Section:
    section = Section.objects.select_for_update().get(pk=section.pk)
    ensure_editable(section.edition)
    if "section_type" in data and data["section_type"] != section.section_type:
        raise Invalid(fields={"section_type": [_("Le type d'une section ne change pas.")]})
    before = _values(section)
    _apply(section, data, SECTION_FIELDS)
    _clean_section(section)
    # Après assainissement : un HTML qui ne change qu'en apparence n'est pas une modification.
    after = _values(section)
    changed = [name for name in SECTION_FIELDS if before[name] != after[name]]
    if changed:
        _save(section, unique_field="code")
        old, new = _diff(before, section, changed)
        record(
            "portal.section_updated",
            actor=actor,
            edition=section.edition,
            obj=section,
            before=old,
            after=new,
        )
    return section


@transaction.atomic
def delete_section(section: Section, *, actor: Actor) -> None:
    """Refusée (400) tant que la section est posée : le message nomme les pages."""
    section = Section.objects.select_for_update().get(pk=section.pk)
    ensure_editable(section.edition)
    slugs = list(
        Page.objects.filter(placements__section=section)
        .order_by("slug")
        .values_list("slug", flat=True)
    )
    if slugs:
        raise Invalid(
            fields={
                "non_field_errors": [
                    _("Section posée sur : %(pages)s. Retirez-la de ces pages d'abord.")
                    % {"pages": ", ".join(slugs)}
                ]
            }
        )
    record(
        "portal.section_deleted",
        actor=actor,
        edition=section.edition,
        obj=section,
        before=snapshot(section),
    )
    section.delete()


def preview_html(edition: Edition, value: str) -> str:
    """Aperçu : le HTML tel qu'il sera enregistré (rien n'est écrit ; édition archivée : 409,
    comme toute écriture)."""
    ensure_editable(edition)
    return sanitize_html(value)


# --- Pages --------------------------------------------------------------------------------


def _check_custom_slug(slug: str) -> None:
    if slug in SITE_ROUTES:
        raise Invalid(fields={"slug": [_("Identifiant réservé à une page du site.")]})


@transaction.atomic
def create_page(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Page:
    """Page personnalisée (``/<langue>/p/<slug>/``) ; les pages du site viennent du seed."""
    ensure_editable(edition)
    _check_custom_slug(data.get("slug", ""))
    page = Page(edition=edition)
    _apply(page, data, PAGE_FIELDS)
    _save(page, unique_field="slug")
    record("portal.page_created", actor=actor, edition=edition, obj=page, after=snapshot(page))
    return page


@transaction.atomic
def update_page(page: Page, data: Mapping[str, Any], *, actor: Actor) -> Page:
    page = Page.objects.select_for_update().get(pk=page.pk)
    ensure_editable(page.edition)
    if page.is_system:
        refused = sorted(set(data) & (set(PAGE_FIELDS) - set(SYSTEM_PAGE_FIELDS)))
        if any(data[name] != getattr(page, name) for name in refused):
            raise Invalid(fields={name: [_("Figé pour une page du site.")] for name in refused})
        allowed = SYSTEM_PAGE_FIELDS
    else:
        if "slug" in data:
            _check_custom_slug(data["slug"])
        allowed = PAGE_FIELDS
    before = _values(page)
    changed = _apply(page, data, allowed)
    if changed:
        _save(page, unique_field="slug")
        old, new = _diff(before, page, changed)
        record(
            "portal.page_updated",
            actor=actor,
            edition=page.edition,
            obj=page,
            before=old,
            after=new,
        )
    return page


@transaction.atomic
def delete_page(page: Page, *, actor: Actor) -> None:
    page = Page.objects.select_for_update().get(pk=page.pk)
    ensure_editable(page.edition)
    if page.is_system:
        raise RuleViolation(_("Une page du site ne se supprime pas."), code=ErrorCode.IN_USE)
    if page.menu_items.exists():
        raise RuleViolation(
            _("Page présente dans un menu : retirez-la du menu d'abord."), code=ErrorCode.IN_USE
        )
    record(
        "portal.page_deleted",
        actor=actor,
        edition=page.edition,
        obj=page,
        before={**snapshot(page), "sections": _section_ids(page)},
    )
    page.delete()  # composition supprimée avec la page (CASCADE)


# --- Composition --------------------------------------------------------------------------


def _section_ids(page: Page) -> list[int]:
    return list(
        PageSection.objects.filter(page=page)
        .order_by("position")
        .values_list("section_id", flat=True)
    )


def composition(page: Page) -> list[PageSection]:
    """Composition relue depuis la base, dans l'ordre."""
    return list(
        PageSection.objects.filter(page=page).select_related("section").order_by("position", "id")
    )


def _write_composition(page: Page, section_ids: Sequence[int]) -> None:
    PageSection.objects.filter(page=page).delete()
    PageSection.objects.bulk_create(
        PageSection(page=page, section_id=section_id, position=index)
        for index, section_id in enumerate(section_ids)
    )


def _locked_page(page: Page) -> Page:
    page = Page.objects.select_for_update().select_related("edition").get(pk=page.pk)
    ensure_editable(page.edition)
    return page


def _record_composition(page: Page, before: list[int], actor: Actor) -> None:
    after = _section_ids(page)
    if after != before:
        record(
            "portal.page_composed",
            actor=actor,
            edition=page.edition,
            obj=page,
            before={"sections": before},
            after={"sections": after},
        )


@transaction.atomic
def attach_section(
    page: Page, section: Section, *, position: int | None = None, actor: Actor
) -> list[PageSection]:
    page = _locked_page(page)
    if section.edition_id != page.edition_id:
        raise Invalid(fields={"section": [_("Section inconnue.")]})
    before = _section_ids(page)
    if section.pk in before:
        raise Invalid(fields={"section": [_("Section déjà posée sur cette page.")]})
    ids = list(before)
    index = len(ids) if position is None else max(0, min(position, len(ids)))
    ids.insert(index, section.pk)
    _write_composition(page, ids)
    _record_composition(page, before, actor)
    return composition(page)


@transaction.atomic
def detach_section(page: Page, section: Section, *, actor: Actor) -> list[PageSection]:
    page = _locked_page(page)
    before = _section_ids(page)
    if section.pk not in before:
        raise Invalid(fields={"section": [_("Section absente de cette page.")]})
    _write_composition(page, [section_id for section_id in before if section_id != section.pk])
    _record_composition(page, before, actor)
    return composition(page)


@transaction.atomic
def reorder_sections(page: Page, section_ids: Sequence[int], *, actor: Actor) -> list[PageSection]:
    """L'ordre est envoyé en **liste complète** : refusé (400) s'il ne correspond pas
    exactement aux sections posées (ni ajout, ni retrait, ni doublon)."""
    page = _locked_page(page)
    before = _section_ids(page)
    if len(section_ids) != len(set(section_ids)) or sorted(section_ids) != sorted(before):
        raise Invalid(
            fields={"sections": [_("La liste doit contenir exactement les sections posées.")]}
        )
    _write_composition(page, section_ids)
    _record_composition(page, before, actor)
    return composition(page)


# --- Menus --------------------------------------------------------------------------------


def _clean_menu_item(item: MenuItem) -> None:
    item.url = _check_url(item.url, "url")
    if bool(item.page_id) == bool(item.url):
        raise Invalid(fields={"page": [_("Choisissez une page ou une adresse, pas les deux.")]})
    if item.page_id and item.page.edition_id != item.edition_id:
        raise Invalid(fields={"page": [_("Page inconnue.")]})


@transaction.atomic
def create_menu_item(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> MenuItem:
    ensure_editable(edition)
    item = MenuItem(edition=edition)
    _apply(item, data, MENU_FIELDS)
    if "position" not in data:
        last = MenuItem.objects.filter(edition=edition, location=item.location).aggregate(
            last=Max("position")
        )["last"]
        item.position = 0 if last is None else last + 1
    _clean_menu_item(item)
    _save(item, unique_field="label_fr")
    record("portal.menu_item_created", actor=actor, edition=edition, obj=item, after=snapshot(item))
    return item


@transaction.atomic
def update_menu_item(item: MenuItem, data: Mapping[str, Any], *, actor: Actor) -> MenuItem:
    item = MenuItem.objects.select_for_update().select_related("edition").get(pk=item.pk)
    ensure_editable(item.edition)
    before = _values(item)
    changed = _apply(item, data, MENU_FIELDS)
    _clean_menu_item(item)
    if changed:
        _save(item, unique_field="label_fr")
        old, new = _diff(before, item, changed)
        record(
            "portal.menu_item_updated",
            actor=actor,
            edition=item.edition,
            obj=item,
            before=old,
            after=new,
        )
    return item


@transaction.atomic
def delete_menu_item(item: MenuItem, *, actor: Actor) -> None:
    item = MenuItem.objects.select_for_update().select_related("edition").get(pk=item.pk)
    ensure_editable(item.edition)
    record(
        "portal.menu_item_deleted",
        actor=actor,
        edition=item.edition,
        obj=item,
        before=snapshot(item),
    )
    item.delete()


@transaction.atomic
def reorder_menu(
    edition: Edition, location: str, item_ids: Sequence[int], *, actor: Actor
) -> list[MenuItem]:
    """Liste complète des entrées de l'emplacement, sinon 400 ; relue depuis la base."""
    ensure_editable(edition)
    if location not in MenuLocation.values:
        raise Invalid(fields={"location": [_("Emplacement inconnu.")]})
    items = list(MenuItem.objects.select_for_update().filter(edition=edition, location=location))
    current = [item.pk for item in sorted(items, key=lambda i: (i.position, i.pk))]
    if len(item_ids) != len(set(item_ids)) or sorted(item_ids) != sorted(current):
        raise Invalid(
            fields={"items": [_("La liste doit contenir exactement les entrées de ce menu.")]}
        )
    by_id = {item.pk: item for item in items}
    for index, item_id in enumerate(item_ids):
        by_id[item_id].position = index
    MenuItem.objects.bulk_update(items, ["position"])
    if list(item_ids) != current:
        record(
            "portal.menu_reordered",
            actor=actor,
            edition=edition,
            before={"location": location, "items": current},
            after={"location": location, "items": list(item_ids)},
        )
    return list(
        MenuItem.objects.filter(edition=edition, location=location)
        .select_related("page")
        .order_by("position", "id")
    )


# --- Seed --------------------------------------------------------------------------------


def seed_portal(edition: Edition) -> dict[str, int]:
    """Pages du site, sections « données » et menu d'en-tête **manquants** (idempotent) ;
    **aucune composition** : le CMS ajoute, il ne remplace pas. Le menu n'est créé que si
    l'édition n'a encore aucune entrée de menu (une suppression volontaire n'est pas
    défaite). Appelé à la création d'une édition et par ``seed_portal``."""
    created = {"pages": 0, "sections": 0, "menu_items": 0}
    pages = {page.slug: page for page in Page.objects.filter(edition=edition)}
    for site_page in SITE_PAGES:
        if site_page.slug not in pages:
            pages[site_page.slug] = Page.objects.create(
                edition=edition,
                slug=site_page.slug,
                title_fr=site_page.title_fr,
                title_en=site_page.title_en,
            )
            created["pages"] += 1
    existing = set(Section.objects.filter(edition=edition).values_list("code", flat=True))
    for code, section_type, title_fr, title_en, config in SEED_SECTIONS:
        if code not in existing:
            Section.objects.create(
                edition=edition,
                code=code,
                section_type=section_type,
                title_fr=title_fr,
                title_en=title_en,
                config=dict(config),
            )
            created["sections"] += 1
    if not MenuItem.objects.filter(edition=edition).exists():
        for position, slug in enumerate(SEED_HEADER_MENU):
            page = pages[slug]
            MenuItem.objects.create(
                edition=edition,
                location=MenuLocation.HEADER,
                label_fr=page.title_fr,
                label_en=page.title_en,
                page=page,
                position=position,
            )
            created["menu_items"] += 1
    return created


# --- Publication (E1, E9) ------------------------------------------------------------------


def last_publication(edition: Edition) -> Publication | None:
    return Publication.objects.filter(edition=edition).order_by("-published_at", "-id").first()


def pending_changes(edition: Edition) -> QuerySet[AuditLog]:
    """Entrées du journal qui changent le portail depuis la dernière mise en ligne."""
    condition = Q()
    for prefix in PORTAL_AFFECTING_ACTIONS:
        condition |= Q(action__startswith=prefix) if prefix.endswith(".") else Q(action=prefix)
    queryset = AuditLog.objects.filter(condition, edition=edition).exclude(
        action="portal.published"
    )
    last = last_publication(edition)
    if last is not None:
        queryset = queryset.filter(at__gt=last.published_at)
    return queryset


def publication_status(edition: Edition) -> dict[str, Any]:
    last = last_publication(edition)
    pending = pending_changes(edition)
    first = pending.order_by("at").values_list("at", flat=True).first()
    return {
        "last_published_at": last.published_at if last else None,
        "release": last.release if last else "",
        "pending_changes": pending.count(),
        "pending_since": first,
    }


@transaction.atomic
def mark_published(edition: Edition, *, release: str = "", actor: Actor) -> Publication:
    """Enregistre une mise en ligne (après ``deploy.sh --portal-only``) : le compteur de
    modifications non publiées repart de zéro."""
    publication = Publication.objects.create(
        edition=edition, published_at=timezone.now(), release=release[:64]
    )
    record(
        "portal.published",
        actor=actor,
        edition=edition,
        after={"release": publication.release, "published_at": publication.published_at},
    )
    return publication


# --- Lecture publique -----------------------------------------------------------------------


def published_placements_prefetch() -> Prefetch:
    return Prefetch(
        "placements",
        queryset=PageSection.objects.filter(section__published=True)
        .select_related("section")
        .order_by("position", "id"),
        to_attr="published_placements",
    )


def public_pages(edition: Edition) -> QuerySet[Page]:
    """Pages servies par le portail : toutes les pages du site, les personnalisées publiées."""
    return Page.objects.filter(Q(is_system=True) | Q(published=True), edition=edition).order_by(
        "-is_system", "slug"
    )


def public_routes(edition: Edition) -> list[str]:
    """Adresses à pré-rendre (FR puis EN), sans doublon : une page du site n'est jamais
    pré-rendue aussi sous ``/p/<slug>/``."""
    routes: list[str] = []
    for page in public_pages(edition):
        for path in page.paths.values():
            if path not in routes:
                routes.append(path)
    return routes
