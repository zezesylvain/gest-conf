"""Stockage privé des fichiers de soumission (règle n° 8, sans adaptation ; plan L3 F2).

Hors racine web (``GESTCONF_PRIVATE_FILES_DIR/submissions``), nom aléatoire, jamais servi
par Apache : seulement par un endpoint authentifié. Un fichier n'est supprimé du disque
qu'après la validation de la transaction qui supprime sa ligne (``on_commit``).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.submissions.models import Submission


def files_root() -> Path:
    return Path(settings.GESTCONF_PRIVATE_FILES_DIR) / "submissions"


def file_path(storage_name: str) -> Path:
    # Nom produit par le serveur (UUID hexadécimal) : jamais de chemin fourni par le client.
    if not storage_name.isalnum():
        raise ValueError(f"Nom de stockage invalide : {storage_name!r}")
    return files_root() / storage_name[:2] / storage_name


def write(data: bytes) -> tuple[str, str]:
    """Écrit le fichier (écriture atomique, droits 0640) ; renvoie (nom, empreinte SHA-256).
    Un fichier écrit dans une transaction ensuite annulée est un orphelin, purgé par
    ``cleanup`` (``submissions.orphan_files``)."""
    storage_name = uuid.uuid4().hex
    path = file_path(storage_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o640)
    os.replace(temporary, path)
    return storage_name, hashlib.sha256(data).hexdigest()


def read(storage_name: str) -> bytes:
    return file_path(storage_name).read_bytes()


def _remove(storage_name: str) -> None:
    file_path(storage_name).unlink(missing_ok=True)


def delete_all(submission: Submission) -> None:
    """Supprime les lignes de fichier d'une soumission, puis les fichiers après validation."""
    names = list(submission.files.values_list("storage_name", flat=True))
    submission.files.all().delete()
    for name in names:
        transaction.on_commit(lambda name=name: _remove(name))


def orphan_files(*, older_than_seconds: int = 86_400) -> list[Path]:
    """Fichiers du disque sans ligne en base, plus vieux que ``older_than_seconds``."""
    import time

    from apps.submissions.models import SubmissionFile

    root = files_root()
    if not root.exists():
        return []
    known = set(SubmissionFile.objects.values_list("storage_name", flat=True))
    limit = time.time() - older_than_seconds
    return [
        path
        for path in root.glob("*/*")
        if path.is_file() and path.name not in known and path.stat().st_mtime < limit
    ]


def purge_orphan_files(dry_run: bool, now) -> int:
    orphans = orphan_files()
    if not dry_run:
        for path in orphans:
            path.unlink(missing_ok=True)
    return len(orphans)
