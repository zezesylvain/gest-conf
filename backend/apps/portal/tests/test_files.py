"""Fichiers publics du portail et photo du profil (L2.4 : E4, E12)."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import ConsentKind, ConsentSource, Profile
from apps.accounts.roles import Role
from apps.accounts.services.account import record_consent
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import Conference, EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core import public_files
from apps.core.actor import Actor
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import PublicFile, PublicFileKind
from apps.portal import services
from apps.portal.models import Page, Section

pytestmark = pytest.mark.django_db

ACTOR = Actor.command("cli:test")
PDF = b"%PDF-1.7\n%%EOF\n"


def png(size=(40, 20)) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, "PNG")
    return output.getvalue()


def upload(edition, data=PDF, name="appel.pdf", kind=PublicFileKind.DOCUMENT, published=True):
    stored = services.upload_file(edition, data=data, name=name, kind=kind, actor=ACTOR)
    if published:
        stored = services.update_file(stored, {"published": True}, actor=ACTOR)
    return stored


@pytest.fixture
def public_edition():
    edition = EditionFactory(status=EditionStatus.PUBLISHED)
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    return edition


def get(url: str, **headers):
    return APIClient().get(url, **headers)


# --- Service public des fichiers ------------------------------------------------------------


def test_published_document_of_current_edition_is_served_as_attachment(public_edition):
    document = upload(public_edition, name="Appel 2027.pdf")
    url = services.public_file_url(document)
    assert url == f"/v1/public/files/{document.uuid}/Appel-2027.pdf"
    response = get(url)
    assert response.status_code == 200
    assert response.content == PDF
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == 'attachment; filename="Appel-2027.pdf"'
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Content-Security-Policy"] == "default-src 'none'; sandbox"
    assert get(url, HTTP_IF_NONE_MATCH=response["ETag"]).status_code == 304


def test_image_is_inline(public_edition):
    image = upload(public_edition, data=png(), name="affiche.png", kind=PublicFileKind.IMAGE)
    response = get(services.public_file_url(image))
    assert response["Content-Disposition"].startswith("inline;")


def test_unpublished_or_draft_edition_files_are_404(public_edition):
    hidden = upload(public_edition, published=False)
    assert get(services.public_file_url(hidden)).status_code == 404
    draft_file = upload(EditionFactory())
    assert get(services.public_file_url(draft_file)).status_code == 404
    assert get("/v1/public/files/00000000-0000-0000-0000-000000000000/x.pdf").status_code == 404


def test_name_in_url_is_cosmetic_uuid_decides(public_edition):
    document = upload(public_edition)
    assert get(f"/v1/public/files/{document.uuid}/autre-nom.pdf").status_code == 200


def test_missing_file_on_disk_is_404(public_edition):
    document = upload(public_edition)
    public_files.file_path(document.storage_name).unlink()
    assert get(services.public_file_url(document)).status_code == 404


# --- Gestion ------------------------------------------------------------------------------------


def test_upload_through_api_checks_content():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.CHAIR))
    path = f"/v1/manage/editions/{edition.pk}/portal/files"
    response = client.post(
        path,
        {"file": SimpleUploadedFile("appel.pdf", b"<html>", "application/pdf"), "kind": "document"},
        format="multipart",
    )
    assert response.status_code == 400
    assert "file" in response.json()["fields"]
    response = client.post(
        path,
        {"file": SimpleUploadedFile("appel.pdf", PDF, "text/html"), "kind": "document"},
        format="multipart",
    )
    body = response.json()
    assert response.status_code == 201
    assert body["content_type"] == "application/pdf"  # type déclaré ignoré
    assert body["published"] is False
    assert body["url"].startswith(f"/v1/public/files/{body['uuid']}/")
    # Aperçu authentifié dans la gestion, même non publié (l'adresse publique répond 404).
    assert client.get(body["preview_url"]).content == PDF
    assert get(body["url"]).status_code == 404


def test_file_in_use_cannot_be_deleted():
    edition = EditionFactory()
    image = upload(edition, data=png(), name="a.png", kind=PublicFileKind.IMAGE)
    section = services.create_section(
        edition,
        {"code": "visuel", "section_type": "image_text", "image": image},
        actor=ACTOR,
    )
    services.set_poster(edition, image, actor=ACTOR)
    with pytest.raises(RuleViolation) as error:
        services.delete_file(image, actor=ACTOR)
    assert "visuel" in str(error.value.message) and "affiche" in str(error.value.message)
    services.update_section(section, {"image": None}, actor=ACTOR)
    services.set_poster(edition, None, actor=ACTOR)
    services.delete_file(image, actor=ACTOR)
    assert not PublicFile.objects.filter(pk=image.pk).exists()


def test_section_image_rules():
    edition = EditionFactory()
    document = upload(edition)
    image = upload(edition, data=png(), name="a.png", kind=PublicFileKind.IMAGE)
    other = upload(EditionFactory(), data=png(), name="b.png", kind=PublicFileKind.IMAGE)
    with pytest.raises(Invalid):  # un document n'est pas une image
        services.create_section(
            edition, {"code": "a", "section_type": "image_text", "image": document}, actor=ACTOR
        )
    with pytest.raises(Invalid):  # image d'une autre édition
        services.create_section(
            edition, {"code": "b", "section_type": "image_text", "image": other}, actor=ACTOR
        )
    with pytest.raises(Invalid):  # seule « image et texte » porte une image
        services.create_section(
            edition, {"code": "c", "section_type": "rich_text", "image": image}, actor=ACTOR
        )


def test_poster_must_be_an_image_of_the_edition():
    edition = EditionFactory()
    with pytest.raises(Invalid):
        services.set_poster(edition, upload(edition), actor=ACTOR)


def test_site_and_composition_expose_published_files_only(public_edition):
    first = upload(public_edition, name="a.pdf")
    upload(public_edition, name="brouillon.pdf", published=False)
    image = upload(
        public_edition, data=png(), name="v.png", kind=PublicFileKind.IMAGE, published=False
    )
    services.set_poster(public_edition, image, actor=ACTOR)
    site = get("/v1/public/portal/site").json()
    assert [item["uuid"] for item in site["documents"]] == [str(first.uuid)]
    assert site["poster"] is None  # affiche non publiée
    section = services.create_section(
        public_edition, {"code": "v", "section_type": "image_text", "image": image}, actor=ACTOR
    )
    services.attach_section(
        Page.objects.get(edition=public_edition, slug="home"), section, actor=ACTOR
    )
    assert get("/v1/public/portal/pages/home").json()["sections"][0]["image"] is None
    services.update_file(image, {"published": True}, actor=ACTOR)
    body = get("/v1/public/portal/pages/home").json()["sections"][0]["image"]
    assert body["url"] == services.public_file_url(image)
    assert get("/v1/public/portal/site").json()["poster"]["uuid"] == str(image.uuid)
    documents = Section.objects.get(edition=public_edition, code="documents")
    services.attach_section(
        Page.objects.get(edition=public_edition, slug="call"), documents, actor=ACTOR
    )
    data = get("/v1/public/portal/pages/call").json()["sections"][0]["data"]
    assert [item["uuid"] for item in data] == [str(first.uuid)]


# --- Photo du profil (E12) ------------------------------------------------------------------


def test_profile_photo_published_only_with_consent():
    user = VerifiedUserFactory()
    client = client_for(user)
    response = client.put(
        "/v1/me/photo",
        {"file": SimpleUploadedFile("Moi.jpg", png(size=(1200, 900)), "image/png")},
        format="multipart",
    )
    assert response.status_code == 400  # extension .jpg, contenu PNG
    response = client.put(
        "/v1/me/photo",
        {"file": SimpleUploadedFile("moi.png", png(size=(1200, 900)), "image/png")},
        format="multipart",
    )
    assert response.status_code == 200
    url = response.json()["photo_url"]
    photo = Profile.objects.get(user=user).photo
    assert (photo.width, photo.height) == (800, 600) and photo.original_name == "photo"
    assert get(url).status_code == 404  # pas de consentement
    own = client.get("/v1/me/photo")  # le titulaire voit sa photo, sans consentement
    assert own.status_code == 200 and own["Cache-Control"] == "private, no-store"
    assert APIClient().get("/v1/me/photo").status_code == 401
    record_consent(
        user, ConsentKind.PHOTO_PUBLICATION, True, source=ConsentSource.ACCOUNT, actor=ACTOR
    )
    assert get(url).status_code == 200
    record_consent(
        user, ConsentKind.PHOTO_PUBLICATION, False, source=ConsentSource.ACCOUNT, actor=ACTOR
    )
    assert get(url).status_code == 404  # retrait : effet immédiat


def test_replacing_and_removing_the_photo_deletes_old_files(django_capture_on_commit_callbacks):
    user = VerifiedUserFactory()
    client = client_for(user)
    with django_capture_on_commit_callbacks(execute=True):
        client.put("/v1/me/photo", {"file": SimpleUploadedFile("a.png", png())}, format="multipart")
    first = Profile.objects.get(user=user).photo
    with django_capture_on_commit_callbacks(execute=True):
        client.put("/v1/me/photo", {"file": SimpleUploadedFile("b.png", png())}, format="multipart")
    assert not PublicFile.objects.filter(pk=first.pk).exists()
    assert not public_files.file_path(first.storage_name).exists()
    with django_capture_on_commit_callbacks(execute=True):
        assert client.delete("/v1/me/photo").json()["photo_url"] is None
    assert not PublicFile.objects.filter(kind=PublicFileKind.PHOTO).exists()


def test_profile_links_must_be_https():
    client = client_for(VerifiedUserFactory())
    response = client.patch("/v1/me/profile", {"website": "http://x.example"}, format="json")
    assert response.status_code == 400
    response = client.patch("/v1/me/profile", {"website": "javascript:alert(1)"}, format="json")
    assert response.status_code == 400
    response = client.patch(
        "/v1/me/profile", {"scholar_url": "https://scholar.google.com/x"}, format="json"
    )
    assert response.json()["scholar_url"] == "https://scholar.google.com/x"


def test_photo_exported_and_deleted_on_anonymization(django_capture_on_commit_callbacks):
    user = VerifiedUserFactory()
    client = client_for(user)
    client.put("/v1/me/photo", {"file": SimpleUploadedFile("a.png", png())}, format="multipart")
    client.patch("/v1/me/profile", {"website": "https://moi.example"}, format="json")
    photo = Profile.objects.get(user=user).photo
    export = export_user_data(user, actor=ACTOR)
    assert export["photo"]["uuid"] == str(photo.uuid)
    assert export["profile"]["website"] == "https://moi.example"
    with django_capture_on_commit_callbacks(execute=True):
        anonymize_user(user, actor=ACTOR, reason="Demande")
    profile = Profile.objects.get(user=user)
    assert profile.photo_id is None and profile.website == ""
    assert not public_files.file_path(photo.storage_name).exists()
