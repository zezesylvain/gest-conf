"""Données personnelles du jour J et des attestations (registre ``apps.core.personal_data``,
RG-18 ; plan L7, K14).

- **Signature** (K18) : export du nom affiché, de la fonction et de la présence d'une image ;
  anonymisation : champs vidés, image effacée (fichier compris). Le rôle de signataire actif
  dans une édition non archivée est déjà une responsabilité qui bloque l'anonymisation
  (``apps.accounts.services.personal_data.active_duties``) ; les pièces émises gardent leur
  nom figé (K14).
- **Pointages** (K4) : export des pointages de la personne (lieu, heure) ; rien à effacer : ils
  ne portent pas de donnée propre, l'inscription à laquelle ils renvoient est anonymisée par
  ``apps.registrations``.
- **Attestations** (K9, K14) : export (nature, édition, émission, révocation, code de
  vérification) ; **conservées** à l'anonymisation, preuve délivrée à la personne, avec leur
  nom figé ; la vérification publique n'affiche alors plus le nom.
- **Lettres d'invitation** (K12, K14) : export (passeport compris) ; à l'anonymisation, le
  **numéro de passeport** est effacé ; la lettre émise reste (nom figé, vérification sans
  nom).
"""

from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.core.personal_data import AnonymizationContext, register_personal_data
from apps.events.models import Certificate, Checkin, InvitationLetter, Signature


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _export(user) -> dict[str, Any]:
    return {
        "signatures": [
            {
                "edition": row.edition.code,
                "display_name": row.display_name,
                "title_fr": row.title_fr,
                "title_en": row.title_en,
                "has_image": bool(row.image_storage_name),
                "image_uploaded_at": _iso(row.image_uploaded_at),
            }
            for row in Signature.objects.filter(user=user)
            .select_related("edition")
            .order_by("edition_id")
        ],
        "checkins": [
            {
                "edition": row.edition.code,
                "session": row.session.title_fr if row.session else None,
                "scanned_at": _iso(row.scanned_at),
                "cancelled": row.cancelled_at is not None,
            }
            for row in Checkin.objects.filter(registration__user=user)
            .select_related("edition", "session")
            .order_by("scanned_at", "id")
        ],
        "certificates": [
            {
                "edition": row.edition.code,
                "nature": row.nature,
                "name": row.name,
                "institution": row.institution,
                "issued_at": _iso(row.issued_at),
                "revoked_at": _iso(row.revoked_at),
                "verification_code": row.verification_code,
            }
            for row in Certificate.objects.filter(user=user)
            .select_related("edition")
            .order_by("issued_at", "id")
        ],
        "invitation_letters": [
            {
                "edition": row.edition.code,
                "status": row.status,
                "passport_name": row.passport_name,
                "nationality": row.nationality,
                "passport_number": row.passport_number,
                "stay_from": _iso(row.stay_from),
                "stay_to": _iso(row.stay_to),
                "embassy": row.embassy,
                "refuse_reason": row.refuse_reason,
                "issued_at": _iso(row.issued_at),
                "verification_code": row.verification_code,
            }
            for row in InvitationLetter.objects.filter(registration__user=user)
            .select_related("edition")
            .order_by("created_at", "id")
        ],
    }


def _anonymize(user, context: AnonymizationContext) -> None:
    from apps.events.services.signatures import IMAGES

    rows = Signature.objects.filter(user=user)
    for name in rows.exclude(image_storage_name="").values_list("image_storage_name", flat=True):
        IMAGES.remove_after_commit(name)
    InvitationLetter.objects.filter(registration__user=user).exclude(passport_number="").update(
        passport_number="", passport_erased_at=timezone.now()
    )
    rows.update(
        display_name="",
        title_fr="",
        title_en="",
        image_storage_name="",
        image_sha256="",
        image_width=None,
        image_height=None,
        image_uploaded_at=None,
    )


def register_events_personal_data() -> None:
    register_personal_data(
        "events.events",
        models=(
            "events.Signature",
            "events.Checkin",
            "events.Certificate",
            "events.InvitationLetter",
        ),
        export=_export,
        anonymize=_anonymize,
        rank=490,
    )
