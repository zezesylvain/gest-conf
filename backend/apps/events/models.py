"""Jour J, attestations et lettres d'invitation (plan L7 §3 ; étude M14, M10, §8.2).

L7.1 : signature du signataire (K18) et pointages (K4). Les attestations et les lettres
d'invitation arrivent avec leurs services (L7.4, L7.5), par migrations additives.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class Signature(TimeStampedModel):
    """Signature d'un signataire dans une édition (K18) : nom affiché, fonction FR et EN,
    image (fichier privé, règle n° 8 ; réencodée en PNG sans métadonnées).

    Écrite par le signataire **seul**, pour son propre compte
    (``apps.events.services.signatures``) : personne ne peut déposer l'image d'un autre. Une
    pièce émise fige le nom, la fonction et l'empreinte de l'image ; la ligne n'est jamais
    supprimée (anonymisation : champs vidés, image effacée).
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="signatures",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("signataire"),
        on_delete=models.RESTRICT,
        related_name="signatures",
    )
    display_name = models.CharField(_("nom affiché"), max_length=150, blank=True, default="")
    title_fr = models.CharField(_("fonction (FR)"), max_length=200, blank=True, default="")
    title_en = models.CharField(_("fonction (EN)"), max_length=200, blank=True, default="")
    image_storage_name = models.CharField(
        _("image (nom de stockage)"), max_length=64, blank=True, default=""
    )
    image_sha256 = models.CharField(
        _("empreinte de l'image"), max_length=64, blank=True, default=""
    )
    image_width = models.PositiveIntegerField(_("largeur (px)"), null=True, blank=True)
    image_height = models.PositiveIntegerField(_("hauteur (px)"), null=True, blank=True)
    image_uploaded_at = models.DateTimeField(_("image déposée le"), null=True, blank=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "user",
        "display_name",
        "title_fr",
        "title_en",
        "image_sha256",
    )

    class Meta:
        db_table = "events_signature"
        verbose_name = _("signature")
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=("edition", "user"), name="events_signature_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.edition_id}:{self.user_id}"

    @property
    def is_complete(self) -> bool:
        """Nom, fonction en français et image : seule une signature complète se désigne."""
        return bool(self.display_name and self.title_fr and self.image_storage_name)


class CheckinMethod(models.TextChoices):
    SCAN = "scan", _("lecture du QR")
    MANUAL = "manual", _("saisie manuelle")


class Checkin(TimeStampedModel):
    """Pointage d'une inscription (K4) : à l'accueil (``session`` nulle) ou à l'entrée d'une
    session (K7). Un pointage vaut présence (RG-16).

    - ``scanned_at`` : heure de l'appareil, bornée par le serveur ; ``received_at`` : heure de
      réception ;
    - ``idempotency_key`` : clé de l'appareil, unique, qui rend la synchronisation hors ligne
      rejouable sans doublon (K5) ;
    - ``active_key`` : ``<inscription>:<session ou 0>`` tant que le pointage n'est pas annulé,
      nulle ensuite : un seul pointage actif par inscription et par lieu (MariaDB n'a pas
      d'index unique partiel) ;
    - annulation (``checkin.manage``, motif, journal), jamais de suppression.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="checkins",
    )
    registration = models.ForeignKey(
        "registrations.Registration",
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="checkins",
    )
    session = models.ForeignKey(
        "program.Session",
        verbose_name=_("session"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="checkins",
    )
    scanned_at = models.DateTimeField(_("pointé le (appareil)"))
    received_at = models.DateTimeField(_("reçu le"))
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("pointé par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    method = models.CharField(_("moyen"), max_length=8, choices=CheckinMethod.choices)
    device = models.CharField(_("appareil"), max_length=64, blank=True, default="")
    idempotency_key = models.CharField(_("clé d'idempotence"), max_length=64, unique=True)
    active_key = models.CharField(
        _("clé du pointage actif"), max_length=32, null=True, blank=True, unique=True
    )
    cancelled_at = models.DateTimeField(_("annulé le"), null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("annulé par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    cancel_reason = models.CharField(
        _("motif d'annulation"), max_length=500, blank=True, default=""
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "registration",
        "session",
        "scanned_at",
        "method",
        "device",
        "cancelled_at",
        "cancel_reason",
    )

    class Meta:
        db_table = "events_checkin"
        verbose_name = _("pointage")
        indexes: ClassVar[list] = [
            models.Index(fields=("edition", "received_at"), name="events_checkin_received"),
            models.Index(fields=("registration", "session"), name="events_checkin_place"),
        ]

    def __str__(self) -> str:
        return f"{self.registration_id}@{self.session_id or 0}"

    @staticmethod
    def place_key(registration_id: int, session_id: int | None) -> str:
        return f"{registration_id}:{session_id or 0}"
