"""Vue factice : met en file N e-mails pendant une requête (voie rapide, plan L1 §8.3)."""

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.urls import path

from apps.communications.services import queue_email


def queue_many(request: HttpRequest, template: str, count: int) -> JsonResponse:
    with transaction.atomic():
        for index in range(count):
            queue_email(
                template_code=f"tests/email/{template}",
                to_email=f"invite{index}@example.org",
                context={"activate_url": f"https://conference.test/#cle-{index}"},
            )
    return JsonResponse({"queued": count})


urlpatterns = [path("queue/<str:template>/<int:count>", queue_many)]
