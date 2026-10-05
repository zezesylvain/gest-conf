"""Stockage privé des fichiers de soumission (règle n° 8, sans adaptation ; plan L3 F2).

Hors racine web (``GESTCONF_PRIVATE_FILES_DIR/submissions``), nom aléatoire, jamais servi
par Apache : seulement par un endpoint authentifié. Un fichier n'est supprimé du disque
qu'après la validation de la transaction qui supprime sa ligne (``on_commit``).
"""

from __future__ import annotations

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


def _remove(storage_name: str) -> None:
    file_path(storage_name).unlink(missing_ok=True)


def delete_all(submission: Submission) -> None:
    """Supprime les lignes de fichier d'une soumission, puis les fichiers après validation."""
    names = list(submission.files.values_list("storage_name", flat=True))
    submission.files.all().delete()
    for name in names:
        transaction.on_commit(lambda name=name: _remove(name))
