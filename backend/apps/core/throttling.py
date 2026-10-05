"""Limitation de débit de l'API (plan L1 §4.7), dans une table de cache dédiée.

Le cache en base purge, au-delà de ``MAX_ENTRIES``, un tiers des clés **par ordre
alphabétique** (``DatabaseCache._cull``, plan §3.5). Les compteurs DRF anonymes par
IP (``throttle_invitation_<ip>``) peuvent être multipliés par un attaquant. Dans une
table commune, leur afflux ferait purger en priorité les clés qui se trient avant
eux : limites de débit et anti-rejeu TOTP d'allauth (L1.3, L1.6), compteurs
``throttle_account_deletion_*`` et ``throttle_data_export_*``. Les compteurs DRF ont
donc leur propre table (alias ``throttle``) : une inondation ne peut plus purger
que des compteurs DRF, et jamais les clés de sécurité du cache « default ».
"""

from django.core.cache import caches
from django.utils.connection import ConnectionProxy
from rest_framework import throttling

# Alias du cache des compteurs DRF (réglage CACHES de config/settings/base.py).
THROTTLE_CACHE_ALIAS = "throttle"


class ScopedRateThrottle(throttling.ScopedRateThrottle):
    """``ScopedRateThrottle`` de DRF, compteurs dans le cache ``throttle``.

    ``ConnectionProxy`` comme ``django.core.cache.cache`` : l'instance du cache est
    résolue à chaque appel (propre au fil d'exécution, et sensible à
    ``override_settings(CACHES=...)`` dans les tests).
    """

    cache = ConnectionProxy(caches, THROTTLE_CACHE_ALIAS)
