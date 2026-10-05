"""Notifications de la cloche (``/v1/me/notifications``, plan L3 F13) : connecté, les
siennes seulement (règle n° 2)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communications import notifications
from apps.communications.serializers import (
    NotificationListSerializer,
    NotificationReadSerializer,
    NotificationSerializer,
    UnreadCountSerializer,
)


class NotificationsView(APIView):
    @extend_schema(operation_id="me_notifications", responses={200: NotificationListSerializer})
    def get(self, request: Request) -> Response:
        return Response(
            {
                "unread": notifications.unread_count(request.user),
                "results": NotificationSerializer(
                    notifications.recent(request.user), many=True
                ).data,
            }
        )


class NotificationsReadView(APIView):
    @extend_schema(
        operation_id="me_notifications_read",
        request=NotificationReadSerializer,
        responses={200: UnreadCountSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = NotificationReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notifications.mark_read(request.user, serializer.validated_data.get("ids"))
        return Response({"unread": notifications.unread_count(request.user)})
