"""Données de test des attestations (plan L7, K9 à K11, K18, K19)."""

from __future__ import annotations

import datetime as dt
import io

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from django.utils import timezone
from PIL import Image

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import make_member
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.events.models import Checkin
from apps.events.services import certificates, signatures
from apps.events.tests.helpers import confirmed

COMMAND = Actor.command("cli:test")


def png(size=(300, 90)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, "PNG")
    return output.getvalue()


def edition(**fields):
    fields.setdefault("start_date", dt.date(2027, 6, 1))
    fields.setdefault("end_date", dt.date(2027, 6, 3))
    fields.setdefault("venue", "Palais de la culture")
    fields.setdefault("city", "Abidjan")
    return EditionFactory(**fields)


def signatory(edition, *, designate=("participation", "presentation", "review", "letter")):
    """Signataire au rôle actif, signature complète, désigné pour les natures données."""
    user = make_member(edition, Role.SIGNATORY)
    signatures.update_details(
        edition,
        user,
        display_name="Pr Awa Diallo",
        title_fr="Présidente du comité d'organisation",
        title_en="Organising committee chair",
        actor=COMMAND,
    )
    signature = signatures.upload_image(edition, user, data=png(), actor=COMMAND)
    for nature in designate:
        certificates.update_template(edition, nature, {"signatory": signature.pk}, actor=COMMAND)
    return user, signature


def present(edition, user=None, *, session=None):
    """Inscription confirmée et pointée (accueil ou session)."""
    registration = confirmed(edition, user)
    now = timezone.now()
    Checkin.objects.create(
        edition=edition,
        registration=registration,
        session=session,
        scanned_at=now,
        received_at=now,
        method="scan",
        idempotency_key=f"test-{registration.pk}-{session.pk if session else 0}",
        active_key=Checkin.place_key(registration.pk, session.pk if session else None),
    )
    return registration


# Mot de passe de test d'un certificat jetable, jamais utilisé ailleurs.
TEST_PASSWORD = "secret-de-test"


def pkcs12_file(password: str = TEST_PASSWORD, *, days: int = 30, cn: str = "Université de test"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=days))
        .sign(key, hashes.SHA256())
    )
    data = pkcs12.serialize_key_and_certificates(
        b"institution",
        key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode()),
    )
    return data, certificate
