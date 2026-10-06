"""Signature du signataire (plan L7, K18 ; Q11) : service et API."""

from __future__ import annotations

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import UserRole
from apps.accounts.roles import Role
from apps.accounts.services.roles import revoke_role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import Invalid, NotAllowed, RuleViolation
from apps.core.models import AuditLog
from apps.events.models import Signature
from apps.events.services import signatures

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


def image(size=(300, 90), *, fmt="PNG", mode="RGB", exif: bytes | None = None) -> bytes:
    output = io.BytesIO()
    options = {"exif": exif} if exif else {}
    Image.new(mode, size, "navy").save(output, fmt, **options)
    return output.getvalue()


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def signatory(edition):
    return make_member(edition, Role.SIGNATORY)


def path(edition, suffix=""):
    return f"/v1/manage/editions/{edition.pk}/signature{suffix}"


# --- Service ------------------------------------------------------------------------------


def test_k18_signatory_fills_own_signature_and_it_becomes_complete(edition, signatory):
    signature = signatures.update_details(
        edition,
        signatory,
        display_name="  Pr Awa Diallo ",
        title_fr="Présidente du comité d'organisation",
        title_en="Organising committee chair",
        actor=COMMAND,
    )
    assert signature.display_name == "Pr Awa Diallo"
    assert not signature.is_complete  # pas encore d'image
    signature = signatures.upload_image(edition, signatory, data=image(), actor=COMMAND)
    assert signature.is_complete
    assert (signature.image_width, signature.image_height) == (300, 90)
    assert Signature.objects.count() == 1
    assert signatures.image_bytes(signature).startswith(b"\x89PNG")


def test_k18_only_an_active_signatory_can_write_a_signature(edition):
    """Défense en profondeur : sans rôle SIGNATORY actif, le service refuse, même appelé
    directement (l'administrateur ne signe pas à la place du signataire)."""
    admin = make_member(edition, Role.ADMIN)
    with pytest.raises(NotAllowed):
        signatures.update_details(
            edition, admin, display_name="X", title_fr="Y", title_en="", actor=COMMAND
        )
    with pytest.raises(NotAllowed):
        signatures.upload_image(edition, admin, data=image(), actor=COMMAND)
    assert not Signature.objects.exists()


def test_k18_revoked_signatory_can_no_longer_write(edition, signatory):
    signatures.update_details(
        edition, signatory, display_name="A", title_fr="B", title_en="", actor=COMMAND
    )
    revoke_role(user_role=UserRole.objects.get(user=signatory), actor=COMMAND, reason="Fin")
    with pytest.raises(NotAllowed):
        signatures.update_details(
            edition, signatory, display_name="C", title_fr="D", title_en="", actor=COMMAND
        )
    # La signature déjà renseignée reste (les pièces émises la citent, figée).
    assert Signature.objects.get(user=signatory).display_name == "A"


def test_jpeg_with_metadata_is_reencoded_as_png_without_metadata(edition, signatory):
    exif = Image.Exif()
    exif[0x010F] = "Appareil secret"  # Make
    data = image(fmt="JPEG", exif=exif.tobytes())
    assert b"Appareil secret" in data
    signature = signatures.upload_image(edition, signatory, data=data, actor=COMMAND)
    stored = signatures.image_bytes(signature)
    assert stored.startswith(b"\x89PNG")
    assert b"Appareil secret" not in stored
    with Image.open(io.BytesIO(stored)) as reread:
        assert not reread.getexif()


def test_large_image_is_reduced(edition, signatory):
    signature = signatures.upload_image(edition, signatory, data=image((2400, 600)), actor=COMMAND)
    assert (signature.image_width, signature.image_height) == (1200, 300)


def test_transparent_png_keeps_its_transparency(edition, signatory):
    signature = signatures.upload_image(edition, signatory, data=image(mode="RGBA"), actor=COMMAND)
    with Image.open(io.BytesIO(signatures.image_bytes(signature))) as reread:
        assert reread.mode == "RGBA"


@pytest.mark.parametrize(
    "data",
    [
        b"%PDF-1.7\n%%EOF\n",  # type annoncé par le contenu : pas une image
        b"GIF89a" + b"\x00" * 64,
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,  # signature PNG, contenu illisible
        image((40, 10)),  # trop petite pour être lisible
    ],
    ids=["pdf", "gif", "truncated-png", "too-small"],
)
def test_bad_images_are_refused(edition, signatory, data):
    with pytest.raises(Invalid) as error:
        signatures.upload_image(edition, signatory, data=data, actor=COMMAND)
    assert "file" in error.value.fields
    assert not Signature.objects.exclude(image_storage_name="").exists()


def test_oversized_file_and_decompression_bomb_are_refused(edition, signatory, monkeypatch):
    with pytest.raises(Invalid):
        signatures.upload_image(
            edition,
            signatory,
            data=image() + b"\x00" * signatures.IMAGE_MAX_BYTES,
            actor=COMMAND,
        )
    monkeypatch.setattr(signatures, "IMAGE_MAX_PIXELS", 1000)
    with pytest.raises(Invalid):
        signatures.upload_image(edition, signatory, data=image(), actor=COMMAND)


def test_replacing_the_image_removes_the_previous_file(
    edition, signatory, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        first = signatures.upload_image(edition, signatory, data=image(), actor=COMMAND)
    old_path = signatures.IMAGES.path(first.image_storage_name)
    assert old_path.exists()
    with django_capture_on_commit_callbacks(execute=True):
        second = signatures.upload_image(edition, signatory, data=image((400, 100)), actor=COMMAND)
    assert second.image_storage_name != first.image_storage_name
    assert not old_path.exists()
    assert signatures.known_images() == [second.image_storage_name]


def test_rg17_signature_changes_are_audited_without_storage_name(edition, signatory):
    signatures.update_details(
        edition, signatory, display_name="Awa", title_fr="Présidente", title_en="", actor=COMMAND
    )
    signature = signatures.upload_image(edition, signatory, data=image(), actor=COMMAND)
    actions = list(AuditLog.objects.order_by("id").values_list("action", flat=True))
    assert actions == ["signature.updated", "signature.image_uploaded"]
    entry = AuditLog.objects.get(action="signature.image_uploaded")
    assert entry.after["image_sha256"] == signature.image_sha256
    assert signature.image_storage_name not in str(entry.after)


def test_archived_edition_is_read_only(edition, signatory):
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    with pytest.raises(RuleViolation):
        signatures.update_details(
            edition, signatory, display_name="A", title_fr="B", title_en="", actor=COMMAND
        )


def test_signature_is_per_edition(edition, signatory):
    other = EditionFactory()
    UserRole.objects.create(
        user=signatory,
        edition=other,
        role=Role.SIGNATORY,
        source="command",
        granted_at=edition.created_at,
    )
    signatures.update_details(
        edition, signatory, display_name="A", title_fr="Présidente", title_en="", actor=COMMAND
    )
    signatures.update_details(
        other, signatory, display_name="A", title_fr="Doyenne", title_en="", actor=COMMAND
    )
    assert sorted(Signature.objects.values_list("title_fr", flat=True)) == [
        "Doyenne",
        "Présidente",
    ]


# --- API -----------------------------------------------------------------------------------


def test_k18_api_round_trip(edition, signatory):
    client = client_for(signatory)
    empty = client.get(path(edition)).json()
    assert empty == {
        "display_name": "",
        "title_fr": "",
        "title_en": "",
        "has_image": False,
        "image_width": None,
        "image_height": None,
        "image_uploaded_at": None,
        "complete": False,
        "updated_at": None,
    }
    response = client.patch(
        path(edition),
        {"display_name": "Pr Awa Diallo", "title_fr": "Présidente"},
        format="json",
    )
    assert response.status_code == 200, response.content
    # PATCH partiel : les champs absents gardent leur valeur.
    response = client.patch(path(edition), {"title_en": "Chair"}, format="json")
    body = response.json()
    assert (body["display_name"], body["title_fr"], body["title_en"]) == (
        "Pr Awa Diallo",
        "Présidente",
        "Chair",
    )
    assert client.get(path(edition, "/image")).status_code == 404
    response = client.put(
        path(edition, "/image"),
        {"file": SimpleUploadedFile("sig.jpg", image(fmt="JPEG"), "image/jpeg")},
        format="multipart",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["complete"] is True and body["has_image"] is True
    assert "image_storage_name" not in body and "image_sha256" not in body
    response = client.get(path(edition, "/image"))
    assert response.status_code == 200
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


def test_k18_each_signatory_sees_only_own_signature(edition, signatory):
    other = make_member(edition, Role.SIGNATORY)
    signatures.update_details(
        edition, signatory, display_name="Awa", title_fr="Présidente", title_en="", actor=COMMAND
    )
    signatures.upload_image(edition, signatory, data=image(), actor=COMMAND)
    client = client_for(other)
    assert client.get(path(edition)).json()["display_name"] == ""
    assert client.get(path(edition, "/image")).status_code == 404


def test_k18_writes_require_recent_authentication(edition, signatory):
    client = client_for(signatory, recent_auth=False)
    assert client.get(path(edition)).status_code == 200
    response = client.patch(path(edition), {"display_name": "X"}, format="json")
    assert (response.status_code, response.json()["code"]) == (403, "reauthentication_required")
    response = client.put(
        path(edition, "/image"),
        {"file": SimpleUploadedFile("sig.png", image(), "image/png")},
        format="multipart",
    )
    assert response.status_code == 403


def test_upload_errors_are_normalized(edition, signatory):
    response = client_for(signatory).put(
        path(edition, "/image"),
        {"file": SimpleUploadedFile("sig.png", b"%PDF-1.7\n", "image/png")},
        format="multipart",
    )
    assert response.status_code == 400
    assert response.json()["fields"]["file"]


def test_signature_routes_refuse_anonymous_and_other_roles(edition):
    assert APIClient().get(path(edition)).status_code == 401
    chair = make_member(edition, Role.CHAIR)
    assert client_for(chair).get(path(edition)).status_code == 403
