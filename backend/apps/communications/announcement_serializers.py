"""Sérialiseurs des annonces et envois groupés (plan L8, N10 et N11)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.communications.models import Announcement, AnnouncementStatus, SendingStatus
from apps.conferences.serializers import LocalDateTimeField
from apps.conferences.services import utc_to_local


def _local(value, edition) -> str | None:
    if value is None:
        return None
    return utc_to_local(value, edition.timezone).strftime("%Y-%m-%dT%H:%M")


class SegmentSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    recipients = serializers.IntegerField()


class AnnouncementSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField(allow_blank=True)
    body_fr = serializers.CharField(allow_blank=True)
    body_en = serializers.CharField(allow_blank=True)
    on_news = serializers.BooleanField()
    on_banner = serializers.BooleanField()
    on_bell = serializers.BooleanField()
    by_email = serializers.BooleanField()
    segment = serializers.CharField(allow_blank=True)
    banner_message_fr = serializers.CharField(allow_blank=True)
    banner_message_en = serializers.CharField(allow_blank=True)
    banner_starts_local = serializers.CharField(allow_null=True)
    banner_ends_local = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=AnnouncementStatus.choices)
    published_at = serializers.DateTimeField(allow_null=True)
    withdrawn_at = serializers.DateTimeField(allow_null=True)
    sending_status = serializers.ChoiceField(choices=SendingStatus.choices)
    recipients_count = serializers.IntegerField()
    emails_count = serializers.IntegerField()
    created_at = serializers.DateTimeField()


def announcement_data(announcement: Announcement) -> dict[str, Any]:
    edition = announcement.edition
    return {
        **{
            name: getattr(announcement, name)
            for name in (
                "id",
                "title_fr",
                "title_en",
                "body_fr",
                "body_en",
                "on_news",
                "on_banner",
                "on_bell",
                "by_email",
                "segment",
                "banner_message_fr",
                "banner_message_en",
                "status",
                "published_at",
                "withdrawn_at",
                "sending_status",
                "recipients_count",
                "emails_count",
                "created_at",
            )
        },
        "banner_starts_local": _local(announcement.banner_starts_at, edition),
        "banner_ends_local": _local(announcement.banner_ends_at, edition),
    }


class SendingStatsSerializer(serializers.Serializer):
    recipients = serializers.IntegerField()
    delivered = serializers.IntegerField()
    emails = serializers.IntegerField()
    sent = serializers.IntegerField()
    queued = serializers.IntegerField()
    failed = serializers.IntegerField()
    cancelled = serializers.IntegerField()
    remaining_hours = serializers.IntegerField()


class AnnouncementDetailSerializer(AnnouncementSerializer):
    sending = SendingStatsSerializer()


class AnnouncementWriteSerializer(serializers.Serializer):
    title_fr = serializers.CharField(max_length=150, required=False)
    title_en = serializers.CharField(max_length=150, required=False, allow_blank=True)
    body_fr = serializers.CharField(required=False, allow_blank=True)
    body_en = serializers.CharField(required=False, allow_blank=True)
    on_news = serializers.BooleanField(required=False)
    on_banner = serializers.BooleanField(required=False)
    on_bell = serializers.BooleanField(required=False)
    by_email = serializers.BooleanField(required=False)
    segment = serializers.CharField(max_length=64, required=False, allow_blank=True)
    banner_message_fr = serializers.CharField(max_length=280, required=False, allow_blank=True)
    banner_message_en = serializers.CharField(max_length=280, required=False, allow_blank=True)
    banner_starts_local = LocalDateTimeField(required=False, allow_null=True)
    banner_ends_local = LocalDateTimeField(required=False, allow_null=True)


class AnnouncementPreviewSerializer(serializers.Serializer):
    subject = serializers.CharField()
    body_text = serializers.CharField()
    body_html = serializers.CharField()
    recipients = serializers.IntegerField()
    opted_out = serializers.IntegerField()
    emails = serializers.IntegerField()
    estimated_hours = serializers.IntegerField()


class CancelledCountSerializer(serializers.Serializer):
    cancelled = serializers.IntegerField()


class PublicBannerItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    message_fr = serializers.CharField()
    message_en = serializers.CharField()
    news = serializers.BooleanField()


class PublicBannerSerializer(serializers.Serializer):
    banner = PublicBannerItemSerializer(allow_null=True)


def public_banner_data(announcement: Announcement | None) -> dict[str, Any]:
    """Liste blanche : titres, messages du bandeau, lien vers l'actualité ; rien d'autre."""
    if announcement is None:
        return {"banner": None}
    return {
        "banner": {
            "id": announcement.pk,
            "title_fr": announcement.title_fr,
            "title_en": announcement.title_en,
            "message_fr": announcement.banner_message_fr,
            "message_en": announcement.banner_message_en,
            "news": announcement.on_news,
        }
    }


class PublicNewsItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    body_fr = serializers.CharField()
    body_en = serializers.CharField()
    published_at = serializers.DateTimeField()


class UnsubscribeSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=400)


class UnsubscribedSerializer(serializers.Serializer):
    edition_title_fr = serializers.CharField()
    edition_title_en = serializers.CharField()


class SubscriptionSerializer(serializers.Serializer):
    subscribed = serializers.BooleanField()
