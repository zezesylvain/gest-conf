"""Stockage privé de fichiers (règle n° 8, sans adaptation), par dossier.

Hors racine web (``GESTCONF_PRIVATE_FILES_DIR/<dossier>``), nom aléatoire produit par le
serveur, droits 0640, écriture atomique ; jamais servi par Apache, seulement par un endpoint
authentifié. Reprend le procédé des fichiers de soumission (plan L3, F2) pour les pièces de
facturation et les justificatifs d'inscription (plan L6).

Un fichier écrit dans une transaction ensuite annulée est un orphelin : ``orphan_files``
le repère, la tâche de conservation de son application le purge.
"""

from __future__ import annotations

import hashlib
import os
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction


@dataclass(frozen=True, slots=True)
class PrivateStore:
    folder: str

    def root(self) -> Path:
        return Path(settings.GESTCONF_PRIVATE_FILES_DIR) / self.folder

    def path(self, storage_name: str) -> Path:
        # Nom produit par le serveur (UUID hexadécimal) : jamais un chemin du client.
        if not storage_name.isalnum():
            raise ValueError(f"Nom de stockage invalide : {storage_name!r}")
        return self.root() / storage_name[:2] / storage_name

    def write(self, data: bytes) -> tuple[str, str]:
        """Écrit le fichier ; renvoie (nom de stockage, empreinte SHA-256)."""
        storage_name = uuid.uuid4().hex
        path = self.path(storage_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o640)
        os.replace(temporary, path)
        return storage_name, hashlib.sha256(data).hexdigest()

    def read(self, storage_name: str) -> bytes:
        return self.path(storage_name).read_bytes()

    def remove_after_commit(self, storage_name: str) -> None:
        """Supprime le fichier après la validation de la transaction qui retire sa ligne."""
        transaction.on_commit(lambda: self.path(storage_name).unlink(missing_ok=True))

    def orphan_files(self, known: Iterable[str], *, older_than_seconds: int = 86_400) -> list[Path]:
        root = self.root()
        if not root.exists():
            return []
        names = set(known)
        limit = time.time() - older_than_seconds
        return [
            path
            for path in root.glob("*/*")
            if path.is_file() and path.name not in names and path.stat().st_mtime < limit
        ]

    def purge_task(self, known: Callable[[], Iterable[str]]):
        """Tâche de conservation (``register_retention_task``) qui purge les orphelins."""

        def purge(dry_run: bool, now) -> int:
            orphans = self.orphan_files(known())
            if not dry_run:
                for path in orphans:
                    path.unlink(missing_ok=True)
            return len(orphans)

        return purge


def sniff(data: bytes) -> str | None:
    """Type d'un fichier d'après son contenu (règle n° 8) : ``pdf``, ``jpeg``, ``png`` ou
    ``None``. L'extension et le type annoncés par le navigateur ne sont jamais crus."""
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    return None
