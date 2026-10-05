"""Nettoyage des PDF en double aveugle (plan L3 F2, préparation de RG-04 ; corpus de L3.0).

Chaque cas place l'identité de l'autrice là où les logiciels la laissent : /Info, XMP,
ancienne révision d'une mise à jour incrémentale, annotation de commentaire signée,
fichier joint. Après nettoyage, aucun octet ne doit la contenir."""

from __future__ import annotations

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    StreamObject,
    TextStringObject,
)

from apps.core.errors import Invalid
from apps.submissions.pdf import check_pdf

NAME = b"Zephyrine Kpangbalo"
XMP = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/'
    b'22-rdf-syntax-ns#"><rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/">'
    b"<dc:creator><rdf:Seq><rdf:li>" + NAME + b"</rdf:li></rdf:Seq></dc:creator>"
    b"</rdf:Description></rdf:RDF></x:xmpmeta>"
)


def _write(writer: PdfWriter) -> bytes:
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _identified() -> PdfWriter:
    writer = PdfWriter()
    writer.add_blank_page(300, 300)
    writer.add_metadata({"/Author": NAME.decode(), "/Creator": "Microsoft Word - Zephyrine"})
    xmp = StreamObject()
    xmp.set_data(XMP)
    xmp.update({NameObject("/Type"): NameObject("/Metadata")})
    writer._root_object[NameObject("/Metadata")] = writer._add_object(xmp)
    return writer


def with_comment_and_attachment() -> bytes:
    writer = _identified()
    comment = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Text"),
            NameObject("/Rect"): ArrayObject([FloatObject(0)] * 4),
            NameObject("/T"): TextStringObject(NAME.decode()),
        }
    )
    link = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject([FloatObject(0)] * 4),
            NameObject("/T"): TextStringObject(NAME.decode()),
            NameObject("/A"): DictionaryObject(
                {
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject("https://doi.org/10.1/x"),
                }
            ),
        }
    )
    writer.pages[0][NameObject("/Annots")] = ArrayObject(
        [writer._add_object(comment), writer._add_object(link)]
    )
    writer.add_attachment("cv.txt", NAME)
    return _write(writer)


def incremental_update() -> bytes:
    first = _write(_identified())
    writer = PdfWriter(io.BytesIO(first), incremental=True)
    writer.add_metadata({"/Author": "Anonyme"})
    data = _write(writer)
    assert NAME in data  # l'ancienne révision reste dans le fichier
    return data


@pytest.mark.parametrize(
    "data",
    [_write(_identified()), with_comment_and_attachment(), incremental_update()],
    ids=["info-xmp", "comment-attachment", "incremental"],
)
def test_f2_identity_is_removed_from_every_byte(data):
    assert NAME in data
    checked = check_pdf(data, anonymize=True)
    assert checked.metadata_removed and checked.pages == 1
    assert NAME not in checked.data
    reader = PdfReader(io.BytesIO(checked.data))
    assert reader.metadata is None and "/Metadata" not in reader.trailer["/Root"]
    assert "/Names" not in reader.trailer["/Root"]  # plus de fichier joint


def test_f2_links_are_kept_without_author():
    checked = check_pdf(with_comment_and_attachment(), anonymize=True)
    annotations = [a.get_object() for a in PdfReader(io.BytesIO(checked.data)).pages[0]["/Annots"]]
    assert [a["/Subtype"] for a in annotations] == ["/Link"]
    assert "/T" not in annotations[0] and annotations[0]["/A"]["/URI"] == "https://doi.org/10.1/x"


def test_open_review_keeps_the_original():
    data = _write(_identified())
    assert check_pdf(data, anonymize=False).data == data


def test_too_many_pages_refused():
    writer = PdfWriter()
    for _ in range(501):
        writer.add_blank_page(10, 10)
    with pytest.raises(Invalid) as error:
        check_pdf(_write(writer), anonymize=True)
    assert "500" in str(error.value.fields["file"][0])
