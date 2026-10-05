"""Sérialiseurs des notifications de la cloche (plan L3, F13)."""

from __future__ import annotations

from rest_framework import serializers

from apps.communications.models import Notification, NotificationKind


class NotificationSerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(choices=NotificationKind.choices, read_only=True)
    payload = serializers.DictField(
        read_only=True,
        help_text="Éléments du texte (référence, titre, échéance), composé par l'interface.",
    )

    class Meta:
        model = Notification
        fields = ("id", "kind", "payload", "created_at", "read_at")
        read_only_fields = fields


class NotificationListSerializer(serializers.Serializer):
    unread = serializers.IntegerField(help_text="Notifications non lues (toutes).")
    results = NotificationSerializer(many=True)


class NotificationReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        max_length=200,
        help_text="Notifications à marquer comme lues ; toutes si absent.",
    )


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()
