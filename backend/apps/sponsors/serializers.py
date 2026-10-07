"""Sérialiseurs des partenaires (plan L8, N5).

Gestion (``sponsors.read``) : fiche complète, contact compris. Public : niveaux et
partenaires publiés, **sans** contact, contribution, statut ni note (liste blanche).
"""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.money import MAX_DIGITS
from apps.sponsors.models import LogoSize, Sponsor, SponsorBenefit, SponsorLevel, SponsorStatus

AMOUNT = {"max_digits": MAX_DIGITS, "decimal_places": 2}


class SponsorLevelSerializer(serializers.ModelSerializer):
    sponsor_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SponsorLevel
        fields = (
            "id",
            "name_fr",
            "name_en",
            "amount",
            "benefits_fr",
            "benefits_en",
            "logo_size",
            "position",
            "sponsor_count",
        )
        read_only_fields = fields


class SponsorLevelWriteSerializer(serializers.Serializer):
    name_fr = serializers.CharField(max_length=100, required=False, allow_blank=True)
    name_en = serializers.CharField(max_length=100, required=False, allow_blank=True)
    amount = serializers.DecimalField(**AMOUNT, required=False, allow_null=True, min_value=0)
    benefits_fr = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    benefits_en = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    logo_size = serializers.ChoiceField(choices=LogoSize.choices, required=False)
    position = serializers.IntegerField(min_value=0, required=False)


class SponsorLogoSerializer(serializers.Serializer):
    url = serializers.CharField()
    preview_url = serializers.CharField(
        help_text="Aperçu dans la gestion (authentifié), partenaire publié ou non."
    )
    width = serializers.IntegerField(allow_null=True)
    height = serializers.IntegerField(allow_null=True)


def logo_data(sponsor: Sponsor) -> dict | None:
    from django.urls import reverse

    from apps.portal.services import public_file_url

    logo = sponsor.logo
    if logo is None:
        return None
    preview = reverse(
        "sponsors:manage-sponsor-logo",
        kwargs={"edition_id": sponsor.edition_id, "sponsor_id": sponsor.pk},
    )
    return {
        "url": public_file_url(logo),
        "preview_url": preview,
        "width": logo.width,
        "height": logo.height,
    }


class SponsorBenefitSerializer(serializers.ModelSerializer):
    class Meta:
        model = SponsorBenefit
        fields = ("id", "label", "delivered_on", "position")
        read_only_fields = fields


class SponsorSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField()
    benefits_due = serializers.IntegerField(read_only=True)
    benefits_delivered = serializers.IntegerField(read_only=True)

    class Meta:
        model = Sponsor
        fields = (
            "id",
            "name",
            "level",
            "published",
            "status",
            "agreed_amount",
            "received_amount",
            "received_on",
            "position",
            "logo",
            "benefits_due",
            "benefits_delivered",
        )
        read_only_fields = fields

    @staticmethod
    @extend_schema_field(SponsorLogoSerializer(allow_null=True))
    def get_logo(sponsor: Sponsor) -> dict | None:
        return logo_data(sponsor)


class SponsorDetailSerializer(SponsorSerializer):
    benefits = SponsorBenefitSerializer(many=True, read_only=True)

    class Meta(SponsorSerializer.Meta):
        fields = (
            *SponsorSerializer.Meta.fields,
            "website",
            "description_fr",
            "description_en",
            "contact_name",
            "contact_email",
            "contact_phone",
            "note",
            "benefits",
        )
        read_only_fields = fields


class SponsorWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    level = serializers.IntegerField(required=False, allow_null=True)
    website = serializers.CharField(max_length=300, required=False, allow_blank=True)
    description_fr = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    description_en = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    published = serializers.BooleanField(required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    contact_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    contact_email = serializers.CharField(max_length=254, required=False, allow_blank=True)
    contact_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=SponsorStatus.choices, required=False)
    agreed_amount = serializers.DecimalField(**AMOUNT, required=False, allow_null=True, min_value=0)
    received_amount = serializers.DecimalField(
        **AMOUNT, required=False, allow_null=True, min_value=0
    )
    received_on = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class SponsorTotalsSerializer(serializers.Serializer):
    currency = serializers.CharField()
    agreed = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)
    received = serializers.DecimalField(max_digits=MAX_DIGITS + 2, decimal_places=2)
    by_status = serializers.DictField(child=serializers.IntegerField())


class SponsorsSerializer(serializers.Serializer):
    totals = SponsorTotalsSerializer()
    sponsors = SponsorSerializer(many=True)


class BenefitWriteSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=200)


class BenefitUpdateSerializer(serializers.Serializer):
    delivered_on = serializers.DateField(allow_null=True)


class LogoUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class PublicSponsorCardSerializer(serializers.Serializer):
    name = serializers.CharField()
    website = serializers.CharField()
    description_fr = serializers.CharField()
    description_en = serializers.CharField()
    logo_url = serializers.CharField()
    logo_width = serializers.IntegerField(allow_null=True)
    logo_height = serializers.IntegerField(allow_null=True)


class PublicSponsorLevelSerializer(serializers.Serializer):
    name_fr = serializers.CharField()
    name_en = serializers.CharField()
    logo_size = serializers.ChoiceField(choices=LogoSize.choices)
    sponsors = PublicSponsorCardSerializer(many=True)


class PublicSponsorsSerializer(serializers.Serializer):
    levels = PublicSponsorLevelSerializer(many=True)
    others = PublicSponsorCardSerializer(many=True)
