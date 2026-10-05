"""Contenus du portail public : CMS-lite (plan L2 §2.2 et §3).

Une **section** est un bloc typé, d'un catalogue fermé que le portail sait rendre ; une
**page** (du site ou personnalisée) en pose une liste ordonnée ; les **menus** d'en-tête et
de pied de page pointent une page ou une URL. Tout est bilingue (``_fr`` / ``_en``, une
colonne anglaise vide se repliant sur le français). Le HTML des corps est assaini à
l'écriture (``sanitizer``) et de nouveau au rendu par le portail.

Aucune donnée personnelle : aucune clé vers un compte (l'auteur des modifications est
dans le journal d'audit).
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.conferences.models import Edition
from apps.core.models import TimeStampedModel
from apps.portal.site import SITE_ROUTES, page_paths


class SectionType(models.TextChoices):
    RICH_TEXT = "rich_text", _("texte riche")
    CTA_BANNER = "cta_banner", _("bandeau d'appel à l'action")
    IMAGE_TEXT = "image_text", _("image et texte")
    EDITION_HERO = "edition_hero", _("en-tête de l'édition")
    KEY_DATES = "key_dates", _("dates clés")
    TRACKS = "tracks", _("thématiques")
    SUBMISSION_TYPES = "submission_types", _("types de communication")
    DOCUMENTS = "documents", _("documents")
    COMMITTEE = "committee", _("comité")


# Types « données » : leur contenu vient des services publics, jamais d'une copie ; la
# section n'en porte que l'habillage (titre, sous-titre, configuration).
DATA_SECTION_TYPES: frozenset[str] = frozenset(
    {
        SectionType.EDITION_HERO,
        SectionType.KEY_DATES,
        SectionType.TRACKS,
        SectionType.SUBMISSION_TYPES,
        SectionType.DOCUMENTS,
        SectionType.COMMITTEE,
    }
)


class Section(TimeStampedModel):
    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="+"
    )
    # « code » et non « key » : le journal d'audit refuse les clés nommées « key ».
    code = models.SlugField(_("code"), max_length=64)
    section_type = models.CharField(_("type"), max_length=20, choices=SectionType.choices)
    title_fr = models.CharField(_("titre (FR)"), max_length=255, blank=True, default="")
    title_en = models.CharField(_("titre (EN)"), max_length=255, blank=True, default="")
    subtitle_fr = models.CharField(_("sous-titre (FR)"), max_length=500, blank=True, default="")
    subtitle_en = models.CharField(_("sous-titre (EN)"), max_length=500, blank=True, default="")
    # HTML en liste blanche, assaini à l'écriture (E3).
    body_fr = models.TextField(_("corps (FR)"), blank=True, default="")
    body_en = models.TextField(_("corps (EN)"), blank=True, default="")
    cta_label_fr = models.CharField(_("bouton 1 (FR)"), max_length=120, blank=True, default="")
    cta_label_en = models.CharField(_("bouton 1 (EN)"), max_length=120, blank=True, default="")
    cta_url = models.CharField(_("lien du bouton 1"), max_length=500, blank=True, default="")
    cta2_label_fr = models.CharField(_("bouton 2 (FR)"), max_length=120, blank=True, default="")
    cta2_label_en = models.CharField(_("bouton 2 (EN)"), max_length=120, blank=True, default="")
    cta2_url = models.CharField(_("lien du bouton 2"), max_length=500, blank=True, default="")
    # Réglages propres au type, bornés par le service (``SECTION_CONFIG``).
    config = models.JSONField(_("configuration"), default=dict, blank=True)
    published = models.BooleanField(_("publiée"), default=True)

    TRANSLATABLE: ClassVar[tuple[str, ...]] = (
        "title",
        "subtitle",
        "body",
        "cta_label",
        "cta2_label",
    )
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
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

    class Meta:
        verbose_name = _("section")
        verbose_name_plural = _("sections")
        ordering = ("code", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="portal_section_code"),
        )

    def __str__(self) -> str:
        return self.code

    @property
    def is_data(self) -> bool:
        return self.section_type in DATA_SECTION_TYPES


class Page(TimeStampedModel):
    """Page du site (``is_system``, slug de ``SITE_ROUTES``) ou page personnalisée."""

    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="+"
    )
    slug = models.SlugField(_("identifiant d'URL"), max_length=64)
    # Marquée d'après SITE_ROUTES à l'enregistrement et par la migration de données.
    is_system = models.BooleanField(_("page du site"), default=False, editable=False)
    title_fr = models.CharField(_("titre (FR)"), max_length=255)
    title_en = models.CharField(_("titre (EN)"), max_length=255, blank=True, default="")
    # Métadonnées (référencement, E7).
    description_fr = models.CharField(_("description (FR)"), max_length=300, blank=True, default="")
    description_en = models.CharField(_("description (EN)"), max_length=300, blank=True, default="")
    published = models.BooleanField(_("publiée"), default=True)
    sections = models.ManyToManyField(
        Section, through="PageSection", related_name="pages", verbose_name=_("sections")
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "slug",
        "is_system",
        "title_fr",
        "title_en",
        "description_fr",
        "description_en",
        "published",
    )

    class Meta:
        verbose_name = _("page")
        verbose_name_plural = _("pages")
        ordering = ("-is_system", "slug", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "slug"], name="portal_page_slug"),
        )

    def __str__(self) -> str:
        return self.slug

    def save(self, *args, **kwargs) -> None:
        # Une page n'est « du site » que si son slug figure dans SITE_ROUTES (créée par le
        # seed) ; le service refuse ces slugs aux pages personnalisées.
        self.is_system = self.slug in SITE_ROUTES
        super().save(*args, **kwargs)

    @property
    def paths(self) -> dict[str, str]:
        return page_paths(self.slug, is_system=self.is_system)


class PageSection(models.Model):
    """Composition : section posée sur une page, à une position. Une section ne se
    supprime pas tant qu'elle est posée (``RESTRICT`` ; le service nomme les pages)."""

    page = models.ForeignKey(
        Page, verbose_name=_("page"), on_delete=models.CASCADE, related_name="placements"
    )
    section = models.ForeignKey(
        Section, verbose_name=_("section"), on_delete=models.RESTRICT, related_name="placements"
    )
    position = models.PositiveSmallIntegerField(_("position"))

    class Meta:
        verbose_name = _("section posée")
        verbose_name_plural = _("sections posées")
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(fields=["page", "section"], name="portal_placement_once"),
            models.UniqueConstraint(fields=["page", "position"], name="portal_placement_pos"),
        )

    def __str__(self) -> str:
        return f"{self.page_id}:{self.position}:{self.section_id}"


class MenuLocation(models.TextChoices):
    HEADER = "header", _("en-tête")
    FOOTER = "footer", _("pied de page")


class MenuItem(TimeStampedModel):
    """Entrée de menu : une page **ou** une URL (``https:``, ``mailto:`` ou adresse interne)."""

    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="+"
    )
    location = models.CharField(_("emplacement"), max_length=8, choices=MenuLocation.choices)
    label_fr = models.CharField(_("libellé (FR)"), max_length=120)
    label_en = models.CharField(_("libellé (EN)"), max_length=120, blank=True, default="")
    page = models.ForeignKey(
        Page,
        verbose_name=_("page"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="menu_items",
    )
    url = models.CharField(_("adresse"), max_length=500, blank=True, default="")
    new_tab = models.BooleanField(_("nouvel onglet"), default=False)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    published = models.BooleanField(_("publiée"), default=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "location",
        "label_fr",
        "label_en",
        "page",
        "url",
        "new_tab",
        "position",
        "published",
    )

    class Meta:
        verbose_name = _("entrée de menu")
        verbose_name_plural = _("entrées de menu")
        ordering = ("location", "position", "id")
        constraints = (
            models.CheckConstraint(
                condition=(Q(page__isnull=False) & Q(url="")) | (Q(page__isnull=True) & ~Q(url="")),
                name="portal_menu_page_xor_url",
            ),
        )
        indexes = (
            models.Index(fields=["edition", "location", "position"], name="portal_menu_pos"),
        )

    def __str__(self) -> str:
        return self.label_fr


class Publication(models.Model):
    """Mise en ligne du portail (E9) : écrite par ``mark_portal_published`` après un build.

    Les modifications postérieures à la dernière mise en ligne se comptent dans le journal
    d'audit (``services.publication_status``).
    """

    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="+"
    )
    published_at = models.DateTimeField(_("mis en ligne le"), db_index=True)
    release = models.CharField(_("version"), max_length=64, blank=True, default="")

    class Meta:
        verbose_name = _("mise en ligne du portail")
        verbose_name_plural = _("mises en ligne du portail")
        ordering = ("-published_at", "-id")

    def __str__(self) -> str:
        return f"{self.edition_id}@{self.published_at:%Y-%m-%d %H:%M}"
