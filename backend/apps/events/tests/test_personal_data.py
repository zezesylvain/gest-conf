"""Données personnelles du jour J (plan L7, K14 ; RG-18) : signature et pointages."""

from __future__ import annotations

import io

import pytest
from django.utils import timezone
from PIL import Image

from apps.accounts.models import UserRole
from apps.accounts.roles import Role
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.services.roles import revoke_role
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import RuleViolation
from apps.events.models import Checkin, Signature
from apps.events.services import signatures
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_registration

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (300, 90), "navy").save(output, "PNG")
    return output.getvalue()


def _signed(edition):
    signatory = make_member(edition, Role.SIGNATORY)
    signatures.update_details(
        edition,
        signatory,
        display_name="Pr Awa Diallo",
        title_fr="Présidente",
        title_en="Chair",
        actor=COMMAND,
    )
    signatures.upload_image(edition, signatory, data=_png(), actor=COMMAND)
    return signatory


def _checkin(registration, *, session=None) -> Checkin:
    now = timezone.now()
    return Checkin.objects.create(
        edition=registration.edition,
        registration=registration,
        session=session,
        scanned_at=now,
        received_at=now,
        method="scan",
        idempotency_key=f"cle-{registration.pk}-{session.pk if session else 0}",
        active_key=Checkin.place_key(registration.pk, session.pk if session else None),
    )


def test_rg18_export_contains_signature_and_checkins():
    edition = EditionFactory()
    signatory = _signed(edition)
    participant = VerifiedUserFactory()
    registration = make_registration(edition, participant, status=RegistrationStatus.CONFIRMED)
    _checkin(registration)
    data = export_user_data(signatory, actor=COMMAND)
    assert data["signatures"] == [
        {
            "edition": edition.code,
            "display_name": "Pr Awa Diallo",
            "title_fr": "Présidente",
            "title_en": "Chair",
            "has_image": True,
            "image_uploaded_at": data["signatures"][0]["image_uploaded_at"],
        }
    ]
    assert data["checkins"] == []
    checkins = export_user_data(participant, actor=COMMAND)["checkins"]
    assert [(item["edition"], item["session"], item["cancelled"]) for item in checkins] == [
        (edition.code, None, False)
    ]


def test_rg18_active_signatory_cannot_be_anonymized():
    """Le rôle de signataire actif est une responsabilité à transmettre (plan L1 §4.9)."""
    edition = EditionFactory()
    signatory = _signed(edition)
    with pytest.raises(RuleViolation) as error:
        anonymize_user(signatory, actor=COMMAND, reason="Demande")
    assert f"{edition.code}:SIGNATORY" in error.value.fields["roles"]


def test_rg18_anonymization_clears_signature_and_removes_image(
    django_capture_on_commit_callbacks,
):
    edition = EditionFactory()
    signatory = _signed(edition)
    signature = Signature.objects.get(user=signatory)
    image_path = signatures.IMAGES.path(signature.image_storage_name)
    assert image_path.exists()
    revoke_role(user_role=UserRole.objects.get(user=signatory), actor=COMMAND, reason="Fin")
    with django_capture_on_commit_callbacks(execute=True):
        anonymize_user(signatory, actor=COMMAND, reason="Demande")
    signature.refresh_from_db()
    assert (signature.display_name, signature.title_fr, signature.title_en) == ("", "", "")
    assert (signature.image_storage_name, signature.image_sha256) == ("", "")
    assert not signature.is_complete
    assert not image_path.exists()


def test_k14_checkins_survive_anonymization_without_personal_data():
    """K14 : les pointages restent (statistiques), rattachés à une inscription anonymisée."""
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    participant = VerifiedUserFactory()
    registration = make_registration(edition, participant, status=RegistrationStatus.CONFIRMED)
    checkin = _checkin(registration)
    anonymize_user(participant, actor=COMMAND, reason="Demande")
    assert Checkin.objects.filter(pk=checkin.pk).exists()
