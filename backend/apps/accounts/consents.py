"""Versions courantes des textes soumis à consentement (plan L1 §4.8, D15).

Les textes eux-mêmes (FR et EN) sont versionnés dans le dépôt, côté Angular. Toute
nouvelle version de la notice fait réapparaître la demande de prise de connaissance
(``privacy_notice_pending`` dans ``/v1/me``). La notice « v0 » est provisoire : le
texte définitif (Q14) bloque l'ouverture de l'appel (L3), pas L1.
"""

from apps.accounts.models import ConsentKind

CURRENT_TEXT_VERSIONS: dict[str, str] = {
    ConsentKind.PRIVACY_NOTICE: "2026-10-v0",
    ConsentKind.DIRECTORY_LISTING: "2026-10-v0",
}
