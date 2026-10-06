"""Sérialiseurs du jour J et des attestations (plan L7 §4)."""

from __future__ import annotations

from rest_framework import serializers

from apps.events.models import Signature


class SignatureSerializer(serializers.Serializer):
    """Signature du signataire connecté (K18) : jamais le nom de stockage de l'image."""

    display_name = serializers.CharField(max_length=150, allow_blank=True)
    title_fr = serializers.CharField(max_length=200, allow_blank=True)
    title_en = serializers.CharField(max_length=200, allow_blank=True)
    has_image = serializers.BooleanField(read_only=True)
    image_width = serializers.IntegerField(read_only=True, allow_null=True)
    image_height = serializers.IntegerField(read_only=True, allow_null=True)
    image_uploaded_at = serializers.DateTimeField(read_only=True, allow_null=True)
    complete = serializers.BooleanField(
        read_only=True, help_text="Nom, fonction en français et image : désignable."
    )
    updated_at = serializers.DateTimeField(read_only=True, allow_null=True)


def signature_data(signature: Signature | None) -> dict:
    if signature is None:
        return {
            "display_name": "",
            "title_fr": "",
            "title_en": "",
            "has_image": False,
            "image_width": None,
            "image_height": None,
            "image_uploaded_at": None,
            "complete": False,
            "updated_at": None,
        }
    return {
        "display_name": signature.display_name,
        "title_fr": signature.title_fr,
        "title_en": signature.title_en,
        "has_image": bool(signature.image_storage_name),
        "image_width": signature.image_width,
        "image_height": signature.image_height,
        "image_uploaded_at": signature.image_uploaded_at,
        "complete": signature.is_complete,
        "updated_at": signature.updated_at,
    }


class SignatureImageUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
