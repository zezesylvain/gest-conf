"""Validateurs du paramétrage de l'édition (plan L1 §3.4)."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

EDITION_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,11}$")


def validate_edition_code(value: str) -> None:
    """Code court de l'édition (``GC26``) : préfixe des références de soumission en L3."""
    if not EDITION_CODE_PATTERN.match(value):
        raise ValidationError(
            _("Code invalide : une majuscule, puis 1 à 11 majuscules ou chiffres (ex. GC26)."),
            code="invalid_edition_code",
        )


def validate_timezone(value: str) -> None:
    """Fuseau IANA (``Africa/Abidjan``), validé par ``zoneinfo`` (paquet tzdata)."""
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationError(_("Fuseau horaire inconnu."), code="invalid_timezone") from exc
