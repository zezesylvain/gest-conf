"""Budget d'envois immédiats par requête (voie rapide des e-mails, plan L1 §8.3)."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.communications.services import fast_path_scope


class EmailFastPathMiddleware:
    """Autorise au plus ``FAST_PATH_MAX_PER_REQUEST`` envois immédiats pendant la requête.

    Sans plafond, la création de 50 invitations ferait 50 allers-retours HTTPS vers
    le fournisseur pendant la requête (plusieurs secondes sous Passenger). Hors
    requête (commandes, cron), aucun budget n'est ouvert : pas de voie rapide.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        with fast_path_scope():
            return self.get_response(request)
