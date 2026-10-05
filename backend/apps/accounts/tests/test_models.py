"""Profil, consentements et validateurs (plan L1 §3.3, §7.1, §12.1)."""

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.countries import ISO_3166_1_ALPHA_2
from apps.accounts.models import Consent, ConsentKind, ConsentSource, Profile
from apps.accounts.tests.factories import UserFactory
from apps.accounts.validators import orcid_checksum_is_valid, validate_country, validate_orcid
from apps.core.actor import Actor
from apps.core.models import AppendOnlyError, AuditLog

COMMAND = Actor.command("cli:operateur")


@pytest.mark.parametrize(
    ("orcid", "valid"),
    [
        ("0000-0002-1825-0097", True),  # exemple de la documentation ORCID
        ("0000-0001-5109-3700", True),
        ("0000-0002-1694-233X", True),
        ("0000-0002-1825-0098", False),
        ("0000-0002-1694-2339", False),
    ],
)
def test_orcid_checksum(orcid, valid):
    assert orcid_checksum_is_valid(orcid) is valid


@pytest.mark.parametrize("value", ["0000-0002-1825-009", "0000000218250097", "abcd-0002-1825-0097"])
def test_orcid_format(value):
    with pytest.raises(ValidationError):
        validate_orcid(value)


def test_country_iso3166():
    assert len(ISO_3166_1_ALPHA_2) == 249
    assert {"CI", "FR", "SN", "CM"} <= ISO_3166_1_ALPHA_2
    validate_country("CI")
    validate_country("")
    for value in ("XX", "ci", "CIV"):
        with pytest.raises(ValidationError):
            validate_country(value)


@pytest.mark.django_db
def test_profile_completeness():
    profile = Profile(user=UserFactory(), first_name="Awa", last_name="Koné", institution="UFHB")
    assert profile.is_complete is False
    profile.country = "CI"
    assert profile.is_complete is True
    profile.first_name = "  "
    assert profile.is_complete is False


def _consent(user, **extra):
    fields = {
        "kind": ConsentKind.DIRECTORY_LISTING,
        "granted": True,
        "text_version": "v0",
        "recorded_at": timezone.now(),
        "source": ConsentSource.ACCOUNT,
        "ip": "203.0.113.9",
    }
    fields.update(extra)
    return Consent.objects.create(user=user, **fields)


@pytest.mark.django_db
def test_consent_is_append_only():
    consent = _consent(UserFactory())
    consent.granted = False
    with pytest.raises(AppendOnlyError):
        consent.save()
    with pytest.raises(AppendOnlyError):
        consent.delete()
    with pytest.raises(AppendOnlyError):
        Consent.objects.update(granted=False)
    with pytest.raises(AppendOnlyError):
        Consent.objects.all().delete()


@pytest.mark.django_db
def test_consent_network_purge_and_redaction_are_audited():
    user, other = UserFactory(), UserFactory()
    old = _consent(user, recorded_at=timezone.now() - timedelta(days=200))
    recent = _consent(user)
    theirs = _consent(other)
    assert Consent.purge_network_before(timezone.now() - timedelta(days=180), actor=COMMAND) == 1
    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.ip, old.granted) == (None, True)
    assert recent.ip == "203.0.113.9"
    assert Consent.redact_network_for_user(user, actor=COMMAND) == 1
    recent.refresh_from_db()
    theirs.refresh_from_db()
    assert recent.ip is None
    assert theirs.ip == "203.0.113.9"
    actions = list(AuditLog.objects.values_list("action", flat=True))
    assert "consent.network_purged" in actions
    assert "consent.network_redacted" in actions
