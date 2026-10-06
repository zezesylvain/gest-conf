"""Signature électronique des pièces (plan L7, K19 ; bilan de L7.0 : ``pyHanko``).

- **Image seule** (défaut) : l'image du signataire est apposée dans le PDF ; aucune
  signature cryptographique. La vérification publique (K10) fait foi.
- **PAdES** (PAdES-B-B, ``ETSI.CAdES.detached``) avec le **certificat de l'institution**
  (PKCS#12). Au dépôt, le fichier est ouvert avec son mot de passe, puis réexporté **sans**
  mot de passe et **rechiffré** par ``GESTCONF_SIGNING_ENCRYPTION_KEYS`` (``MultiFernet``,
  comme les secrets de la 2FA) avant d'être écrit hors racine web. Le mot de passe n'est
  jamais gardé ; la clé n'est jamais servie. Un certificat dans un fichier n'est pas un
  dispositif qualifié : la signature n'est pas « qualifiée » au sens eIDAS.
- **Prestataire qualifié** (Q17) : interface prévue, aucun prestataire branché.

``pyHanko`` n'est importé qu'au moment de signer (0,3 s d'import, bilan de L7.0).
"""

from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass

from cryptography import x509
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives.serialization import NoEncryption, pkcs12
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.errors import ErrorCode, Invalid, RuleViolation

KEY_MAX_BYTES = 64 * 1024


def unavailable(message) -> RuleViolation:
    return RuleViolation(message, code=ErrorCode.SIGNING_UNAVAILABLE)


def cipher() -> MultiFernet:
    """La première clé chiffre, toutes déchiffrent (rotation)."""
    keys = [key.strip() for key in settings.GESTCONF_SIGNING_ENCRYPTION_KEYS if key.strip()]
    if not keys:
        raise unavailable(
            _("Signature PAdES indisponible : GESTCONF_SIGNING_ENCRYPTION_KEYS n'est pas définie.")
        )
    return MultiFernet([Fernet(key.encode()) for key in keys])


@dataclass(frozen=True, slots=True)
class PreparedKey:
    encrypted: bytes
    subject: str
    not_after: dt.datetime


def prepare_key(data: bytes, password: str) -> PreparedKey:
    """PKCS#12 déposé → clé et certificats réexportés sans mot de passe, puis chiffrés.

    Refusé : fichier illisible ou mot de passe faux, clé ou certificat absent, certificat
    pas encore ou plus valable, usage de clé sans signature.
    """
    if len(data) > KEY_MAX_BYTES:
        raise Invalid(fields={"file": [_("Fichier de 64 ko au plus.")]})
    try:
        key, certificate, others = pkcs12.load_key_and_certificates(data, password.encode())
    except (ValueError, TypeError) as error:
        raise Invalid(
            fields={"file": [_("Fichier PKCS#12 illisible ou mot de passe incorrect.")]}
        ) from error
    if key is None or certificate is None:
        raise Invalid(fields={"file": [_("Le fichier doit contenir une clé et son certificat.")]})
    now = timezone.now()
    if not (certificate.not_valid_before_utc <= now < certificate.not_valid_after_utc):
        raise Invalid(fields={"file": [_("Certificat hors de sa période de validité.")]})
    try:
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound:
        usage = None
    if usage is not None and not (usage.digital_signature or usage.content_commitment):
        raise Invalid(fields={"file": [_("Certificat sans usage de signature.")]})
    exported = pkcs12.serialize_key_and_certificates(
        b"gest-conf", key, certificate, others or None, NoEncryption()
    )
    subject = certificate.subject.rfc4514_string()[:255]
    return PreparedKey(cipher().encrypt(exported), subject, certificate.not_valid_after_utc)


def _decrypt(encrypted: bytes) -> bytes:
    try:
        return cipher().decrypt(encrypted)
    except InvalidToken as error:
        raise unavailable(
            _("Certificat de signature indéchiffrable : clé de chiffrement changée ?")
        ) from error


def check_key(encrypted: bytes) -> None:
    """Le certificat déposé se déchiffre encore (avant d'activer PAdES ou d'émettre)."""
    _decrypt(encrypted)


def sign_pdf(pdf: bytes, encrypted_key: bytes, *, reason: str, location: str) -> bytes:
    """Signature PAdES-B-B du PDF par le certificat de l'institution."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    signer = signers.SimpleSigner.load_pkcs12_data(_decrypt(encrypted_key), other_certs=[])
    if signer is None:
        raise unavailable(_("Certificat de signature inutilisable."))
    writer = IncrementalPdfFileWriter(io.BytesIO(pdf))
    meta = signers.PdfSignatureMetadata(
        field_name="Signature",
        subfilter=fields.SigSeedSubFilter.PADES,
        reason=reason,
        location=location,
        md_algorithm="sha256",
    )
    return signers.sign_pdf(writer, meta, signer=signer).getvalue()
