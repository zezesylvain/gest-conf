"""Sérialiseurs du CMS du portail : gestion (lecture et écriture) et lecture publique."""

from __future__ import annotations

from typing import Any, ClassVar

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import ProfileTitle
from apps.accounts.roles import OcFunction
from apps.conferences.serializers import PublicEditionSerializer
from apps.core.models import PublicFile
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
    "image",
    "config",
    "published",
)


class PublicFileRefSerializer(serializers.ModelSerializer):
    """Fichier public tel que le voient les pages : adresse, dimensions, titre."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = PublicFile
        fields = (
            "uuid",
            "url",
            "title_fr",
            "title_en",
            "extension",
            "content_type",
            "size",
            "width",
            "height",
        )
        read_only_fields = fields

    def get_url(self, public_file: PublicFile) -> str:
        from apps.portal.services import public_file_url

        return public_file_url(public_file)


class PublicFileSerializer(PublicFileRefSerializer):
    """Gestion des fichiers de l'édition (documents et images)."""

    uses = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField(
        help_text="Aperçu dans la gestion (authentifié), publié ou non."
    )

    class Meta:
        model = PublicFile
        fields = (
            "preview_url",
            "id",
            "uuid",
            "kind",
            "original_name",
            "url",
            "title_fr",
            "title_en",
            "extension",
            "content_type",
            "size",
            "width",
            "height",
            "position",
            "published",
            "uses",
            "created_at",
        )
        read_only_fields = (
            "id",
            "uuid",
            "kind",
            "original_name",
            "url",
            "extension",
            "content_type",
            "size",
            "width",
            "height",
            "uses",
            "created_at",
        )

    def get_preview_url(self, public_file: PublicFile) -> str:
        from django.urls import reverse

        return reverse(
            "portal:manage-portal-files-content",
            kwargs={"edition_id": public_file.edition_id, "item_id": public_file.pk},
        )

    def get_uses(self, public_file: PublicFile) -> list[str]:
        from apps.portal.services import file_uses

        return file_uses(public_file)


# Natures téléversables dans la gestion du portail (les photos passent par /v1/me/photo).
PORTAL_FILE_KIND_CHOICES = [("document", "document"), ("image", "image")]


class FileUploadSerializer(serializers.Serializer):
    file = serializers.FileField(
        help_text="Document : PDF, DOCX, ODT, ZIP ; image : PNG, JPEG, WebP."
    )
    kind = serializers.ChoiceField(choices=PORTAL_FILE_KIND_CHOICES)
    title_fr = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    title_en = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class PosterSerializer(serializers.Serializer):
    file = serializers.IntegerField(allow_null=True, help_text="Image de l'édition, ou null.")
    poster = PublicFileRefSerializer(read_only=True, allow_null=True)


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
    image_ref = PublicFileRefSerializer(source="image", read_only=True, allow_null=True)

    class Meta:
        model = Section
        fields = ("id", *SECTION_CONTENT_FIELDS, "image_ref", "is_data", "pages", "updated_at")
        read_only_fields = ("id", "image_ref", "is_data", "pages", "updated_at")

    @extend_schema_field(PageRefSerializer(many=True))
    def get_pages(self, section: Section) -> list[dict]:
        # ``placements__page`` préchargé par la vue (pas de requête par section).
        pages = [placement.page for placement in section.placements.all()]
        return PageRefSerializer(sorted(pages, key=lambda page: page.slug), many=True).data


class SectionWriteSerializer(serializers.ModelSerializer):
    """Écriture : les contrôles métier (HTML, liens, configuration) sont dans le service."""

    config = serializers.JSONField(required=False)
    image = serializers.PrimaryKeyRelatedField(
        queryset=PublicFile.objects.all(), allow_null=True, required=False
    )

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


class PlacedSectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Section
        fields = ("id", "code", "section_type", "title_fr", "title_en", "published")
        read_only_fields = fields


class PlacementSerializer(serializers.ModelSerializer):
    section = PlacedSectionSerializer(read_only=True)

    class Meta:
        model = PageSection
        fields = ("position", "section")
        read_only_fields = fields


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
    image = serializers.SerializerMethodField()

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
            "image",
            "config",
            "data",
        )
        read_only_fields = fields

    @extend_schema_field(PublicFileRefSerializer(allow_null=True))
    def get_image(self, section: Section) -> dict | None:
        """Image de la section, seulement si elle est publiée (sinon son adresse ferait 404)."""
        image = section.image
        return PublicFileRefSerializer(image).data if image and image.published else None

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
            return site["committees"].get(section.config.get("committee"))
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


class PublicCommitteeMemberSerializer(serializers.Serializer):
    """Fiche publique d'un membre consentant (E5) : jamais d'adresse e-mail."""

    title = serializers.ChoiceField(choices=ProfileTitle.choices)
    name = serializers.CharField()
    chair = serializers.BooleanField(help_text="Présidence (CHAIR ou SC_CHAIR).")
    function = serializers.ChoiceField(
        choices=OcFunction.choices, help_text="Fonction au CO, vide hors CO."
    )
    institution = serializers.CharField()
    country = serializers.CharField(help_text="Code ISO 3166-1 alpha-2 ou vide.")
    website = serializers.CharField()
    scholar_url = serializers.CharField()
    linkedin_url = serializers.CharField()
    photo_url = serializers.CharField(allow_null=True)


class PublicCommitteeSerializer(serializers.Serializer):
    members = PublicCommitteeMemberSerializer(many=True)
    others = serializers.IntegerField(help_text="Membres sans consentement à l'annuaire.")


class PublicCommitteesSerializer(serializers.Serializer):
    scientific = PublicCommitteeSerializer()
    organizing = PublicCommitteeSerializer()


class PublicSiteSerializer(serializers.Serializer):
    edition = PublicEditionSerializer()
    poster = PublicFileRefSerializer(allow_null=True)
    documents = PublicFileRefSerializer(many=True)
    committees = PublicCommitteesSerializer()
    site_url = serializers.CharField(help_text="Origine publique du portail, sans barre finale.")
