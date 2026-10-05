"""Fichiers publics (E4, plan L2 §6) : type par le contenu, réencodage, stockage."""

import io
import os
import sys
import time
import zipfile

import pytest
from django.db import transaction
from PIL import Image

from apps.core import public_files
from apps.core.errors import Invalid
from apps.core.models import PublicFile, PublicFileKind

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def zip_bytes(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


DOCX = zip_bytes({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w:document/>"})
ODT = zip_bytes({"mimetype": b"application/vnd.oasis.opendocument.text", "content.xml": b"<x/>"})
LATEX = zip_bytes({"modele.tex": b"\\documentclass{article}", "README": b"lisez-moi"})


def image_bytes(fmt: str, size=(2400, 1600), exif: bool = False, mode="RGB") -> bytes:
    image = Image.new(mode, size, "navy" if mode != "1" else 1)
    output = io.BytesIO()
    options = {}
    if exif:
        data = Image.Exif()
        data[0x010F] = "Appareil"  # Make
        data[0x8825] = {1: "N", 2: (5.0, 20.0, 0.0)}  # GPS
        options["exif"] = data.tobytes()
    image.save(output, fmt, **options)
    return output.getvalue()


def store(data: bytes, name: str, kind=PublicFileKind.DOCUMENT) -> PublicFile:
    return public_files.store(data=data, name=name, kind=kind)


@pytest.mark.parametrize(
    ("data", "name", "extension"),
    [
        (PDF, "appel.pdf", "pdf"),
        (DOCX, "modele.docx", "docx"),
        (ODT, "modele.odt", "odt"),
        (LATEX, "latex.zip", "zip"),
    ],
)
def test_documents_detected_by_content(data, name, extension):
    stored = store(data, name)
    assert stored.extension == extension
    assert stored.content_type == public_files.DOCUMENT_TYPES[extension]
    assert public_files.read(stored) == data
    assert stored.storage_name.endswith(f".{extension}") and name not in stored.storage_name
    path = public_files.file_path(stored.storage_name)
    assert oct(path.stat().st_mode & 0o777) == "0o640"


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (b"<html><script>alert(1)</script></html>", "appel.pdf"),  # HTML déguisé
        (b"MZ\x90\x00binaire", "outil.pdf"),  # exécutable Windows
        (b"#!/bin/sh\nrm -rf /", "script.zip"),
        (b"<svg onload=alert(1)>", "logo.png"),  # SVG refusé (scriptable)
        (b"", "vide.pdf"),
    ],
)
def test_unknown_or_disguised_content_is_refused(data, name):
    with pytest.raises(Invalid):
        store(data, name)
    assert not PublicFile.objects.exists()


def test_extension_must_match_content():
    with pytest.raises(Invalid) as error:
        store(PDF, "appel.docx")
    assert "extension" in str(error.value.fields["file"][0]).lower()


def test_image_kind_refuses_documents_and_document_kind_refuses_images():
    with pytest.raises(Invalid):
        store(PDF, "appel.pdf", kind=PublicFileKind.IMAGE)
    with pytest.raises(Invalid):
        store(image_bytes("PNG"), "a.png", kind=PublicFileKind.DOCUMENT)


def test_size_limits(monkeypatch):
    monkeypatch.setattr(public_files, "MAX_DOCUMENT_SIZE", 100)
    with pytest.raises(Invalid):
        store(PDF + b"x" * 200, "gros.pdf")


def test_zip_bomb_guard(monkeypatch):
    monkeypatch.setattr(public_files, "MAX_ZIP_UNCOMPRESSED", 1000)
    with pytest.raises(Invalid):
        store(zip_bytes({"zeros.bin": b"\0" * 5000}), "bombe.zip")


@pytest.mark.parametrize(
    ("fmt", "name", "extension"),
    [("PNG", "a.png", "png"), ("JPEG", "a.jpeg", "jpg"), ("WEBP", "a.webp", "webp")],
)
def test_images_reencoded_resized_without_metadata(fmt, name, extension):
    stored = store(image_bytes(fmt, exif=fmt != "PNG"), name, kind=PublicFileKind.IMAGE)
    assert (stored.width, stored.height) == (1600, 1067)
    reread = Image.open(io.BytesIO(public_files.read(stored)))
    assert reread.format == public_files.PILLOW_FORMATS[extension]
    assert not reread.getexif()
    assert stored.extension == extension


def test_photo_is_800px_and_loses_its_name():
    stored = store(image_bytes("JPEG", exif=True), "Jeanne-Dupont.jpg", kind=PublicFileKind.PHOTO)
    assert max(stored.width, stored.height) == 800
    assert stored.original_name == "photo"


def test_decompression_bomb_refused(monkeypatch):
    monkeypatch.setattr(public_files, "MAX_PIXELS", 1_000_000)
    data = image_bytes("PNG", size=(2000, 2000), mode="1")
    with pytest.raises(Invalid):
        store(data, "bombe.png", kind=PublicFileKind.IMAGE)


def test_corrupted_image_refused():
    data = image_bytes("PNG")[:60]
    with pytest.raises(Invalid):
        store(data, "casse.png", kind=PublicFileKind.IMAGE)


def test_fallback_without_pillow_refuses_exif_jpeg(monkeypatch):
    """Repli de E4 (V28 en échec) : JPEG portant un EXIF refusé, autres images gardées."""
    jpeg_with_exif = image_bytes("JPEG", exif=True)
    png = image_bytes("PNG", size=(10, 10))
    monkeypatch.setitem(sys.modules, "PIL", None)
    with pytest.raises(Invalid):
        store(jpeg_with_exif, "a.jpg", kind=PublicFileKind.IMAGE)
    stored = store(png, "a.png", kind=PublicFileKind.IMAGE)
    assert public_files.read(stored) == png and stored.width is None


def test_delete_removes_file_after_commit(django_capture_on_commit_callbacks):
    stored = store(PDF, "appel.pdf")
    path = public_files.file_path(stored.storage_name)
    with django_capture_on_commit_callbacks(execute=True):
        public_files.delete(stored)
    assert not path.exists() and not PublicFile.objects.exists()


def test_rollback_leaves_an_orphan_found_by_cleanup():
    with pytest.raises(RuntimeError), transaction.atomic():
        stored = store(PDF, "appel.pdf")
        name = stored.storage_name
        raise RuntimeError
    path = public_files.file_path(name)
    assert path.exists()
    assert public_files.orphan_files() == []  # trop récent : peut-être en cours
    old = time.time() - 2 * 86_400
    os.utime(path, (old, old))
    assert public_files.orphan_files() == [path]
    assert public_files.purge_orphan_files(False, None) == 1
    assert not path.exists()


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("Appel à communications 2027.pdf", "Appel-communications-2027.pdf"),
        ("../../etc/passwd", "passwd.pdf"),
        ("", "fichier.pdf"),
    ],
)
def test_safe_download_name(original, expected):
    assert public_files.safe_download_name(original, "pdf") == expected


def test_integrity_reports_rows_without_file():
    stored = store(PDF, "appel.pdf")
    assert public_files.check_missing_files() == []
    public_files.file_path(stored.storage_name).unlink()
    assert str(stored.uuid) in public_files.check_missing_files()[0]
