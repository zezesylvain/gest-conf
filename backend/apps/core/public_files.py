"""Fichiers publics (E4, plan L2 §2.5 et §6 ; règle n° 8 adaptée aux fichiers publics par nature).

- **Type vérifié par le contenu** (signature), jamais par le nom ni le type déclaré ; l'extension
  du nom doit correspondre au type détecté. Liste blanche courte : PDF, DOCX, ODT, ZIP
  (modèle LaTeX) pour les documents ; PNG, JPEG, WebP pour les images.
- **Tailles** : 10 Mio (documents), 5 Mio (images, avant réencodage).
- **Images réencodées** par Pillow (V28) : redimensionnées (1 600 px, 800 px pour une photo),
  métadonnées supprimées (EXIF, dont la position GPS). Sans Pillow (repli de E4) : JPEG portant
  un EXIF refusé, pas de redimensionnement.
- **Stockage hors racine web** (``GESTCONF_FILES_DIR``), nom aléatoire, écriture atomique ;
  fichier supprimé **après** la validation de la transaction (``on_commit``).
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import secrets
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.core.errors import Invalid
from apps.core.models import PublicFile, PublicFileKind

MiB = 1024 * 1024
MAX_DOCUMENT_SIZE = 10 * MiB
MAX_IMAGE_SIZE = 5 * MiB
IMAGE_MAX_SIDE = {PublicFileKind.IMAGE: 1600, PublicFileKind.PHOTO: 800, PublicFileKind.LOGO: 600}
# Garde contre les « bombes » de décompression (pixels, et contenu des ZIP).
MAX_PIXELS = 40_000_000
MAX_ZIP_ENTRIES = 500
MAX_ZIP_UNCOMPRESSED = 50 * MiB

DOCUMENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "odt": "application/vnd.oasis.opendocument.text",
    "zip": "application/zip",
}
IMAGE_TYPES = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}
EXTENSION_ALIASES = {"jpeg": "jpg"}
PILLOW_FORMATS = {"png": "PNG", "jpg": "JPEG", "webp": "WEBP"}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class Detected:
    extension: str
    content_type: str


def files_root() -> Path:
    return Path(settings.GESTCONF_FILES_DIR) / "public"


def file_path(storage_name: str) -> Path:
    return files_root() / storage_name[:2] / storage_name


def safe_download_name(original_name: str, extension: str) -> str:
    """Nom proposé au téléchargement : ASCII sûr, extension du type détecté."""
    stem = Path(original_name).stem
    stem = _SAFE_NAME.sub("-", stem).strip("-._")[:80] or "fichier"
    return f"{stem}.{extension}"


def _refuse(message) -> Invalid:
    return Invalid(fields={"file": [message]})


def _declared_extension(name: str) -> str:
    extension = Path(name).suffix.lower().lstrip(".")
    return EXTENSION_ALIASES.get(extension, extension)


def _zip_kind(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise _refuse(_("Archive illisible.")) from exc
    if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_ZIP_UNCOMPRESSED:
        raise _refuse(_("Archive trop volumineuse une fois décompressée."))
    names = {entry.filename for entry in entries}
    if "word/document.xml" in names and "[Content_Types].xml" in names:
        return "docx"
    if "mimetype" in names and archive.read("mimetype").strip() == DOCUMENT_TYPES["odt"].encode():
        return "odt"
    return "zip"


def detect(data: bytes, name: str, kind: str) -> Detected:
    """Type d'après la signature ; refus si inconnu, non permis pour ``kind`` ou si
    l'extension du nom ne correspond pas."""
    if data.startswith(b"%PDF-"):
        extension = "pdf"
    elif data.startswith(b"PK\x03\x04"):
        extension = _zip_kind(data)
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif data.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise _refuse(_("Type de fichier non accepté."))
    allowed = DOCUMENT_TYPES if kind == PublicFileKind.DOCUMENT else IMAGE_TYPES
    if extension not in allowed:
        raise _refuse(_("Type de fichier non accepté pour cet usage."))
    if _declared_extension(name) != extension:
        raise _refuse(_("L'extension du nom ne correspond pas au contenu du fichier."))
    return Detected(extension=extension, content_type=allowed[extension])


def _has_exif(data: bytes) -> bool:
    return b"Exif\x00\x00" in data[:65536]


def reencode_image(data: bytes, extension: str, kind: str) -> tuple[bytes, int | None, int | None]:
    """Image redimensionnée et sans métadonnées ; repli sans Pillow (E4)."""
    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError:  # repli : Pillow absent de l'hébergement (V28 en échec)
        if extension == "jpg" and _has_exif(data):
            raise _refuse(
                _("Photo refusée : elle contient des métadonnées (EXIF). Exportez-la sans.")
            ) from None
        return data, None, None
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            if source.width * source.height > MAX_PIXELS:
                raise _refuse(_("Image trop grande."))
            image = source.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise _refuse(_("Image illisible.")) from exc
    side = IMAGE_MAX_SIDE[kind]
    image.thumbnail((side, side))
    if extension == "jpg" and image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    output = io.BytesIO()
    options = {"quality": 85, "optimize": True} if extension in ("jpg", "webp") else {}
    # Aucune métadonnée transmise (ni exif, ni icc, ni texte) : Pillow n'en écrit pas.
    image.save(output, PILLOW_FORMATS[extension], **options)
    return output.getvalue(), image.width, image.height


def _write(storage_name: str, data: bytes) -> None:
    path = file_path(storage_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)


def _remove(storage_name: str) -> None:
    file_path(storage_name).unlink(missing_ok=True)


def store(
    *,
    data: bytes,
    name: str,
    kind: str,
    edition=None,
    title_fr: str = "",
    title_en: str = "",
    published: bool = False,
) -> PublicFile:
    """Vérifie, réencode s'il le faut, écrit le fichier et crée la ligne.

    À appeler dans la transaction du service métier. Si elle est annulée après l'écriture, le
    fichier reste sans ligne : ``orphan_files`` le retrouve et ``cleanup`` le supprime.
    """
    limit = MAX_DOCUMENT_SIZE if kind == PublicFileKind.DOCUMENT else MAX_IMAGE_SIZE
    if not data:
        raise _refuse(_("Fichier vide."))
    if len(data) > limit:
        raise _refuse(_("Fichier trop volumineux (%(max)s Mio au plus).") % {"max": limit // MiB})
    detected = detect(data, name, kind)
    width = height = None
    if kind != PublicFileKind.DOCUMENT:
        data, width, height = reencode_image(data, detected.extension, kind)
    storage_name = f"{secrets.token_hex(16)}.{detected.extension}"
    _write(storage_name, data)
    try:
        return PublicFile.objects.create(
            uuid=uuid.uuid4(),
            edition=edition,
            kind=kind,
            storage_name=storage_name,
            # Une photo de profil ne garde pas son nom d'origine (donnée personnelle possible).
            original_name="photo" if kind == PublicFileKind.PHOTO else Path(name).name[:255],
            extension=detected.extension,
            content_type=detected.content_type,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            width=width,
            height=height,
            title_fr=title_fr,
            title_en=title_en,
            published=published,
        )
    except Exception:
        _remove(storage_name)
        raise


def delete(public_file: PublicFile) -> None:
    """Supprime la ligne, puis le fichier **après** validation de la transaction."""
    storage_name = public_file.storage_name
    public_file.delete()
    transaction.on_commit(lambda: _remove(storage_name))


def read(public_file: PublicFile) -> bytes:
    return file_path(public_file.storage_name).read_bytes()


def orphan_files(*, older_than_seconds: int = 86_400) -> list[Path]:
    """Fichiers du stockage sans ligne ``PublicFile`` (transaction annulée après l'écriture),
    plus vieux que ``older_than_seconds`` (pas un téléversement en cours)."""
    import time

    root = files_root()
    if not root.exists():
        return []
    known = set(PublicFile.objects.values_list("storage_name", flat=True))
    limit = time.time() - older_than_seconds
    return sorted(
        path
        for path in root.glob("*/*")
        if path.is_file() and path.name not in known and path.stat().st_mtime < limit
    )


def purge_orphan_files(dry_run: bool, now) -> int:
    """Tâche de ``cleanup`` : supprime les fichiers orphelins (hygiène du stockage, toujours
    appliquée, ce n'est pas une durée de conservation de D15)."""
    orphans = orphan_files()
    if not dry_run:
        for path in orphans:
            path.unlink(missing_ok=True)
    return len(orphans)


def check_missing_files() -> list[str]:
    """Contrôle d'intégrité : lignes ``PublicFile`` dont le fichier a disparu (restauration
    partielle, suppression manuelle) ; elles répondraient 404 sur le portail."""
    missing = [
        str(item.uuid)
        for item in PublicFile.objects.only("uuid", "storage_name")
        if not file_path(item.storage_name).exists()
    ]
    if not missing:
        return []
    return [f"Fichiers publics absents du stockage : {len(missing)} ({', '.join(missing[:5])}…)."]
