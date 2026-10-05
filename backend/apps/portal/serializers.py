"""Sérialiseurs du CMS du portail : gestion (lecture et écriture) et lecture publique."""

from __future__ import annotations

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.conferences.serializers import PublicEditionSerializer
from apps.portal.models import MenuItem, MenuLocation, Page, PageSection, Section, SectionType

SECTION_CONTENT_FIELDS = (
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


class PagePathsSerializer(serializers.Serializer):
    fr = serializers.CharField()
    en = serializers.CharField()


class PageRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ("id", "slug", "title_fr", "is_system")
        read_only_fields = fields


# --- Gestion ---------------------------------------------------------------------------------


class SectionSerializer(serializers.ModelSerializer):
    """Section avec les pages qui la portent (« posée sur »)."""

    pages = serializers.SerializerMethodField()
    is_data = serializers.BooleanField(read_only=True)

    class Meta:
        model = Section
        fields = ("id", *SECTION_CONTENT_FIELDS, "is_data", "pages", "updated_at")
        read_only_fields = ("id", "is_data", "pages", "updated_at")

    @extend_schema_field(PageRefSerializer(many=True))
    def get_pages(self, section: Section) -> list[dict]:
        # ``placements__page`` préchargé par la vue (pas de requête par section).
        pages = [placement.page for placement in section.placements.all()]
        return PageRefSerializer(sorted(pages, key=lambda page: page.slug), many=True).data


class SectionWriteSerializer(serializers.ModelSerializer):
    """Écriture : les contrôles métier (HTML, liens, configuration) sont dans le service."""

    config = serializers.JSONField(required=False)

    class Meta:
        model = Section
        fields = SECTION_CONTENT_FIELDS
        extra_kwargs: ClassVar[dict] = {
            "section_type": {"required": True},
            "code": {"required": True},
        }


class PreviewSerializer(serializers.Serializer):
    body_fr = serializers.CharField(required=False, allow_blank=True, default="")
    body_en = serializers.CharField(required=False, allow_blank=True, default="")


class PlacementSerializer(serializers.ModelSerializer):
    section = serializers.SerializerMethodField()

    class Meta:
        model = PageSection
        fields = ("position", "section")
        read_only_fields = fields

    @extend_schema_field(
        serializers.DictField(help_text="id, code, section_type, title_fr, title_en, published")
    )
    def get_section(self, placement: PageSection) -> dict[str, Any]:
        section = placement.section
        return {
            "id": section.pk,
            "code": section.code,
            "section_type": section.section_type,
            "title_fr": section.title_fr,
            "title_en": section.title_en,
            "published": section.published,
        }


class PageSerializer(serializers.ModelSerializer):
    paths = PagePathsSerializer(read_only=True)
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = (
            "id",
            "slug",
            "is_system",
            "title_fr",
            "title_en",
            "description_fr",
            "description_en",
            "published",
            "paths",
            "sections",
            "updated_at",
        )
        read_only_fields = ("id", "is_system", "paths", "sections", "updated_at")

    @extend_schema_field(PlacementSerializer(many=True))
    def get_sections(self, page: Page) -> list[dict]:
        # ``placements__section`` préchargé par la vue ; tri en mémoire.
        placements = sorted(page.placements.all(), key=lambda item: (item.position, item.pk))
        return PlacementSerializer(placements, many=True).data


class SectionRefSerializer(serializers.Serializer):
    section = serializers.IntegerField(min_value=1)
    position = serializers.IntegerField(min_value=0, required=False)


class SectionOrderSerializer(serializers.Serializer):
    sections = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)


class MenuItemSerializer(serializers.ModelSerializer):
    page = serializers.PrimaryKeyRelatedField(
        queryset=Page.objects.all(), allow_null=True, required=False
    )
    page_ref = PageRefSerializer(source="page", read_only=True, allow_null=True)

    class Meta:
        model = MenuItem
        fields = (
            "id",
            "location",
            "label_fr",
            "label_en",
            "page",
            "page_ref",
            "url",
            "new_tab",
            "position",
            "published",
        )
        read_only_fields = ("id", "page_ref")


class MenuOrderSerializer(serializers.Serializer):
    location = serializers.ChoiceField(choices=MenuLocation.choices)
    items = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=True)


class PublicationStatusSerializer(serializers.Serializer):
    last_published_at = serializers.DateTimeField(allow_null=True)
    release = serializers.CharField(allow_blank=True)
    pending_changes = serializers.IntegerField()
    pending_since = serializers.DateTimeField(allow_null=True)


# --- Public ----------------------------------------------------------------------------------


class PublicPageSerializer(serializers.ModelSerializer):
    paths = PagePathsSerializer(read_only=True)

    class Meta:
        model = Page
        fields = (
            "slug",
            "is_system",
            "title_fr",
            "title_en",
            "description_fr",
            "description_en",
            "paths",
        )
        read_only_fields = fields


class PublicSectionSerializer(serializers.ModelSerializer):
    """Section publiée : habillage, contenu assaini, et données pour les types « données »."""

    data = serializers.SerializerMethodField()

    class Meta:
        model = Section
        fields = (
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
            "data",
        )
        read_only_fields = fields

    @extend_schema_field(
        serializers.JSONField(
            help_text="Données des types « données » (null pour les autres), voir le portail."
        )
    )
    def get_data(self, section: Section) -> Any:
        site = self.context.get("site")
        if site is None or not section.is_data:
            return None
        if section.section_type == SectionType.EDITION_HERO:
            return site["edition"]
        if section.section_type == SectionType.KEY_DATES:
            limit = section.config.get("limit")
            dates = site["edition"]["key_dates"]
            return dates[:limit] if limit else dates
        if section.section_type == SectionType.TRACKS:
            return site["edition"]["tracks"]
        if section.section_type == SectionType.SUBMISSION_TYPES:
            return site["edition"]["submission_types"]
        if section.section_type == SectionType.DOCUMENTS:
            limit = section.config.get("limit")
            documents = site["documents"]
            return documents[:limit] if limit else documents
        if section.section_type == SectionType.COMMITTEE:
            return site["committees"].get(section.config.get("committee"), [])
        return None


class PublicCompositionSerializer(serializers.Serializer):
    page = PublicPageSerializer()
    sections = PublicSectionSerializer(many=True)


class PublicRoutesSerializer(serializers.Serializer):
    routes = serializers.ListField(child=serializers.CharField())
    expected = serializers.IntegerField(
        help_text="Nombre de routes à pré-rendre, vérifié au build."
    )
    pages = PublicPageSerializer(many=True)


class PublicMenuItemSerializer(serializers.Serializer):
    label_fr = serializers.CharField()
    label_en = serializers.CharField()
    href_fr = serializers.CharField()
    href_en = serializers.CharField()
    new_tab = serializers.BooleanField()
    page = serializers.CharField(allow_null=True, help_text="Slug de la page visée, sinon null.")


class PublicSiteSerializer(serializers.Serializer):
    edition = PublicEditionSerializer()
    documents = serializers.ListField(child=serializers.DictField())
    committees = serializers.DictField(child=serializers.ListField(child=serializers.DictField()))
