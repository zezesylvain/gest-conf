"""Routes des notifications de la cloche (plan L3, F13)."""

from django.urls import path

from apps.communications.views import NotificationsReadView, NotificationsView

app_name = "communications"

urlpatterns = [
    path("me/notifications", NotificationsView.as_view(), name="me-notifications"),
    path("me/notifications/read", NotificationsReadView.as_view(), name="me-notifications-read"),
]
