"""Outils HTTP transverses : adresse IP du client (plan L1 §4.2, « Adresse IP du client »)."""

import ipaddress

from django.conf import settings
from django.http import HttpRequest
from rest_framework.request import Request


def client_ip(request: HttpRequest | Request) -> str | None:
    """Adresse IP du client, déterminée comme le fait DRF pour la limitation de débit.

    Même logique que ``BaseThrottle.get_ident`` (``rest_framework/throttling.py``)
    avec ``NUM_PROXIES = GESTCONF_TRUSTED_PROXY_COUNT`` :

    - 0 (valeur par défaut, sûre) : ``REMOTE_ADDR``, sans lire ``X-Forwarded-For``,
      que le client peut forger ;
    - N > 0 : la N-ième adresse en partant de la fin de ``X-Forwarded-For``
      (celle qu'a ajoutée le premier des N mandataires de confiance), ou
      ``REMOTE_ADDR`` si l'en-tête est absent.

    Deux écarts assumés avec DRF, sans effet sur une requête bien formée : un
    en-tête ``X-Forwarded-For`` vide est traité comme absent, et une valeur qui
    n'est pas une adresse IP donne ``None`` (le journal d'audit stocke une IP
    valide ou rien, alors que DRF n'en fait qu'une clé de cache).
    """
    meta = request.META
    remote_addr = meta.get("REMOTE_ADDR") or None
    forwarded_for = meta.get("HTTP_X_FORWARDED_FOR", "")
    trusted_proxies = settings.GESTCONF_TRUSTED_PROXY_COUNT

    candidate = remote_addr
    if trusted_proxies > 0 and forwarded_for.strip():
        addresses = forwarded_for.split(",")
        candidate = addresses[-min(trusted_proxies, len(addresses))].strip()

    if candidate is None:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return None
    return candidate
