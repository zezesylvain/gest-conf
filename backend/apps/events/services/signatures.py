"""Signature du signataire (K18, plan L7 ; Q11).

Le signataire renseigne **sa propre** signature dans l'édition où il tient le rôle
``SIGNATORY`` : nom affiché, fonction (FR, EN) et image. Personne d'autre ne peut l'écrire,
pas même l'administrateur : la vue exige ``signature.manage``, que seul le rôle donne, et ce
service revérifie le rôle actif (défense en profondeur, règle n° 2).

Image : PNG ou JPEG d'au plus 1 Mo, type vérifié par contenu puis **réencodée en PNG** (ni
métadonnées, ni contenu caché), dimensions bornées, stockée hors racine web (règle n° 8).
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services.roles import ensure_editable
from apps.core.audit import record, snapshot
from apps.core.errors import Invalid, NotAllowed
from apps.core.private_files import PrivateStore, sniff
from apps.events.models import Signature

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.conferences.models import Edition
    from apps.core.actor import Actor

IMAGES = PrivateStore("signatures")
IMAGE_MAX_BYTES = 1024 * 1024
# Garde contre les « bombes » de décompression, avant tout décodage complet.
IMAGE_MAX_PIXELS = 25_000_000
# Image réduite à 1 200 px de côté au plus (une signature imprimée fait quelques cm) ; en
# dessous de 60 px de large ou 20 px de haut, ce n'est pas une signature lisible.
IMAGE_MAX_SIDE = 1200
IMAGE_MIN_WIDTH, IMAGE_MIN_HEIGHT = 60, 20


def is_signatory(edition: Edition, user: User) -> bool:
    return UserRole.objects.filter(
        edition=edition, user=user, role=Role.SIGNATORY, status=UserRoleStatus.ACTIVE
    ).exists()


def _check_signatory(edition: Edition, user: User) -> None:
    if not is_signatory(edition, user):
        raise NotAllowed(_("Seul un signataire de l'édition renseigne sa signature."))


def signature_of(edition: Edition, user: User) -> Signature | None:
    return Signature.objects.filter(edition=edition, user=user).first()


def _locked(edition: Edition, user: User) -> Signature:
    signature, _created = Signature.objects.select_for_update().get_or_create(
        edition=edition, user=user
    )
    return signature


@transaction.atomic
def update_details(
    edition: Edition,
    user: User,
    *,
    display_name: str,
    title_fr: str,
    title_en: str,
    actor: Actor,
) -> Signature:
    """Nom affiché et fonction (FR, EN) du signataire ; journal ``signature.updated``."""
    ensure_editable(edition)
    _check_signatory(edition, user)
    signature = _locked(edition, user)
    before = snapshot(signature)
    signature.display_name = display_name.strip()
    signature.title_fr = title_fr.strip()
    signature.title_en = title_en.strip()
    signature.save()
    record(
        "signature.updated",
        actor=actor,
        edition=edition,
        obj=signature,
        before=before,
        after=snapshot(signature),
    )
    return signature


def normalize_image(
    data: bytes,
    *,
    max_side: int = IMAGE_MAX_SIDE,
    min_width: int = IMAGE_MIN_WIDTH,
    min_height: int = IMAGE_MIN_HEIGHT,
) -> tuple[bytes, int, int]:
    """PNG ou JPEG (d'après le contenu) → PNG réencodé, sans métadonnées, borné en taille.
    Sert aussi à l'en-tête des attestations (bornes propres)."""
    from PIL import Image, UnidentifiedImageError

    if len(data) > IMAGE_MAX_BYTES:
        raise Invalid(fields={"file": [_("Image d'1 Mo au plus.")]})
    if sniff(data) not in ("png", "jpeg"):
        raise Invalid(fields={"file": [_("PNG ou JPEG attendu.")]})
    try:
        with Image.open(io.BytesIO(data)) as source:
            # Dimensions lues dans l'en-tête, avant le décodage complet.
            if source.width * source.height > IMAGE_MAX_PIXELS:
                raise Invalid(fields={"file": [_("Image trop grande.")]})
            source.load()
            image = source.copy()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise Invalid(fields={"file": [_("Image illisible.")]}) from exc
    image.thumbnail((max_side, max_side))
    if image.width < min_width or image.height < min_height:
        raise Invalid(fields={"file": [_("Image trop petite pour être lisible.")]})
    if image.mode not in ("RGB", "RGBA", "L", "LA"):
        image = image.convert("RGBA")
    output = io.BytesIO()
    # Aucune métadonnée transmise (ni exif, ni icc, ni texte) : Pillow n'en écrit pas.
    image.save(output, "PNG", optimize=True)
    return output.getvalue(), image.width, image.height


@transaction.atomic
def upload_image(edition: Edition, user: User, *, data: bytes, actor: Actor) -> Signature:
    """Image de signature (remplace la précédente) ; journal ``signature.image_uploaded``
    avec l'empreinte seulement."""
    ensure_editable(edition)
    _check_signatory(edition, user)
    png, width, height = normalize_image(data)
    signature = _locked(edition, user)
    before = snapshot(signature)
    previous = signature.image_storage_name
    storage_name, digest = IMAGES.write(png)
    signature.image_storage_name = storage_name
    signature.image_sha256 = digest
    signature.image_width, signature.image_height = width, height
    signature.image_uploaded_at = timezone.now()
    signature.save()
    if previous:
        IMAGES.remove_after_commit(previous)
    record(
        "signature.image_uploaded",
        actor=actor,
        edition=edition,
        obj=signature,
        before=before,
        after=snapshot(signature),
    )
    return signature


def image_bytes(signature: Signature) -> bytes:
    return IMAGES.read(signature.image_storage_name)


def known_images() -> list[str]:
    return list(
        Signature.objects.exclude(image_storage_name="").values_list(
            "image_storage_name", flat=True
        )
    )
