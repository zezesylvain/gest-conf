"""Validateurs des champs du profil (plan L1 §3.3)."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.accounts.countries import ISO_3166_1_ALPHA_2

ORCID_PATTERN = re.compile(r"^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$")


def orcid_checksum_is_valid(orcid: str) -> bool:
    """Clé de contrôle ISO 7064 MOD 11-2 d'un ORCID (``0000-0002-1825-0097``)."""
    digits = orcid.replace("-", "")
    total = 0
    for char in digits[:-1]:
        total = (total + int(char)) * 2
    result = (12 - total % 11) % 11
    expected = "X" if result == 10 else str(result)
    return digits[-1] == expected


def validate_orcid(value: str) -> None:
    if not value:
        return
    if not ORCID_PATTERN.match(value) or not orcid_checksum_is_valid(value):
        raise ValidationError(
            _("Identifiant ORCID invalide (forme 0000-0000-0000-000X)."), code="invalid_orcid"
        )


def validate_country(value: str) -> None:
    if value and value not in ISO_3166_1_ALPHA_2:
        raise ValidationError(_("Code pays ISO 3166-1 inconnu."), code="invalid_country")
