"""Contrôle et nettoyage des PDF déposés (plan L3 F2 ; résultats L3.0, §11 du plan).

Le nettoyage **reconstruit** un document à partir des seules pages :
- ni catalogue d'origine (XMP, fichiers joints, formulaires, JavaScript), ni ``/Info`` ;
- ``/Metadata``, ``/PieceInfo``, ``/LastModified`` et ``/Thumb`` retirés des pages ;
- annotations réduites aux liens, sans auteur ni date ;
- objets orphelins supprimés (un objet copié puis retiré resterait écrit, défaut de L3.0).

Limites connues (consigne affichée à l'auteur ; contrôle assisté du texte en P2) : le
texte du document (nom dans le corps ou l'en-tête) et les EXIF des images JPEG incorporées
ne sont pas traités.
"""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, NameObject

from apps.core.errors import Invalid

logger = logging.getLogger(__name__)

MAX_PAGES = 500
PAGE_KEYS_DROPPED = ("/Metadata", "/PieceInfo", "/LastModified", "/Thumb")
LINK_KEYS_DROPPED = ("/T", "/Contents", "/NM", "/M", "/Popup")


@dataclass(frozen=True, slots=True)
class CheckedPdf:
    data: bytes
    pages: int
    metadata_removed: bool


def _refuse(message) -> Invalid:
    return Invalid(fields={"file": [message]})


def _read(data: bytes) -> PdfReader:
    if not data.startswith(b"%PDF-"):
        raise _refuse(_("Le fichier n'est pas un PDF."))
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        encrypted = reader.is_encrypted
    except (PdfReadError, ValueError, KeyError, TypeError, IndexError) as error:
        logger.info("PDF illisible : %s", type(error).__name__)
        raise _refuse(_("PDF illisible ou endommagé.")) from error
    # Avant de compter les pages : un PDF chiffré refuse toute lecture de son contenu.
    if encrypted:
        raise _refuse(_("PDF protégé par mot de passe : déposez une version sans protection."))
    try:
        pages = len(reader.pages)
    except (PdfReadError, ValueError, KeyError, TypeError, IndexError) as error:
        logger.info("PDF illisible : %s", type(error).__name__)
        raise _refuse(_("PDF illisible ou endommagé.")) from error
    if pages == 0:
        raise _refuse(_("PDF sans page."))
    if pages > MAX_PAGES:
        raise _refuse(_("PDF trop long (%(max)s pages au plus).") % {"max": MAX_PAGES})
    return reader


def _clean(reader: PdfReader) -> bytes:
    writer = PdfWriter()
    for page in reader.pages:
        # Filtrer AVANT la copie : un objet copié puis retiré resterait écrit.
        for key in PAGE_KEYS_DROPPED:
            page.pop(NameObject(key), None)
        annotations = page.get("/Annots")
        if annotations is not None:
            links = []
            for reference in annotations.get_object():
                annotation = reference.get_object()
                if annotation.get("/Subtype") == "/Link":
                    for key in LINK_KEYS_DROPPED:
                        annotation.pop(NameObject(key), None)
                    links.append(reference)
            if links:
                page[NameObject("/Annots")] = ArrayObject(links)
            else:
                del page[NameObject("/Annots")]
        writer.add_page(page)
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    # Pas de dictionnaire /Info, pas même le « Producer » que pypdf ajoute par défaut.
    writer.metadata = None
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def check_pdf(data: bytes, *, anonymize: bool) -> CheckedPdf:
    """Contrôle le PDF (signature, lecture, chiffrement, nombre de pages) ; en double
    aveugle (``anonymize``), renvoie la version nettoyée. Lève ``Invalid`` (champ ``file``)."""
    reader = _read(data)
    pages = len(reader.pages)
    if not anonymize:
        return CheckedPdf(data=data, pages=pages, metadata_removed=False)
    try:
        cleaned = _clean(reader)
    except Exception as error:  # pypdf : toute erreur de réécriture refuse le fichier
        logger.info("Réécriture du PDF impossible : %s", type(error).__name__)
        raise _refuse(
            _("Ce PDF ne peut pas être anonymisé automatiquement : réexportez-le puis réessayez.")
        ) from error
    return CheckedPdf(data=cleaned, pages=pages, metadata_removed=True)
