"""Jour J, attestations et lettres d'invitation (plan L7 §3 ; étude M14, M10, §8.2).

L7.1 : signature du signataire (K18) et pointages (K4) ; L7.4 : attestations (K9 à K11, K19,
RG-16), leur paramétrage et leurs gabarits ; L7.5 : lettres d'invitation (K12).
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


# --- Attestations (K9 à K11, K19 ; RG-16) ---------------------------------------------------------


class DocumentNature(models.TextChoices):
    """Pièces émises et signées : trois natures d'attestation (K9), et la lettre d'invitation
    (K12, L7.5), qui partage le paramétrage (signataire, gabarit)."""

    PARTICIPATION = "participation", _("attestation de participation")
    PRESENTATION = "presentation", _("attestation de communication")
    REVIEW = "review", _("attestation d'évaluation")
    LETTER = "letter", _("lettre d'invitation")


CERTIFICATE_NATURES = (
    DocumentNature.PARTICIPATION,
    DocumentNature.PRESENTATION,
    DocumentNature.REVIEW,
)


class SigningMode(models.TextChoices):
    """Signature des pièces (K19) : image seule (défaut), PAdES avec le certificat de
    l'institution, ou prestataire de signature qualifiée (Q17 : aucun n'est branché)."""

    IMAGE = "image", _("image de la signature")
    PADES = "pades", _("signature électronique PAdES")
    PROVIDER = "provider", _("prestataire de signature qualifiée")


class SignatureLayout(models.TextChoices):
    SIGNATURE_RIGHT = "signature_right", _("signature à droite, QR à gauche")
    SIGNATURE_LEFT = "signature_left", _("signature à gauche, QR à droite")


class CertificateSettings(TimeStampedModel):
    """Paramétrage des pièces d'une édition (K9, K19), créé à la première lecture.

    - mode de signature et attestation d'évaluation (désactivée par défaut, réponse du
      commanditaire) ;
    - en-tête du modèle officiel (image privée, réencodée en PNG) et disposition ;
    - certificat PAdES de l'institution : PKCS#12 ouvert au dépôt, puis rechiffré par
      ``GESTCONF_SIGNING_ENCRYPTION_KEYS`` (fichier privé) ; son mot de passe n'est pas
      gardé, la clé n'est jamais servie.
    """

    edition = models.OneToOneField(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="certificate_settings",
    )
    signing_mode = models.CharField(
        _("signature"), max_length=10, choices=SigningMode.choices, default=SigningMode.IMAGE
    )
    review_enabled = models.BooleanField(_("attestation d'évaluation"), default=False)
    layout = models.CharField(
        _("disposition"),
        max_length=16,
        choices=SignatureLayout.choices,
        default=SignatureLayout.SIGNATURE_RIGHT,
    )
    header_storage_name = models.CharField(
        _("en-tête (nom de stockage)"), max_length=64, blank=True, default=""
    )
    header_sha256 = models.CharField(
        _("empreinte de l'en-tête"), max_length=64, blank=True, default=""
    )
    header_width = models.PositiveIntegerField(
        _("largeur de l'en-tête (px)"), null=True, blank=True
    )
    header_height = models.PositiveIntegerField(
        _("hauteur de l'en-tête (px)"), null=True, blank=True
    )
    key_storage_name = models.CharField(
        _("certificat de signature (nom de stockage)"), max_length=64, blank=True, default=""
    )
    key_subject = models.CharField(
        _("titulaire du certificat"), max_length=255, blank=True, default=""
    )
    key_not_after = models.DateTimeField(_("certificat valable jusqu'au"), null=True, blank=True)
    key_uploaded_at = models.DateTimeField(_("certificat déposé le"), null=True, blank=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "signing_mode",
        "review_enabled",
        "layout",
        "header_sha256",
        "key_subject",
        "key_not_after",
    )

    class Meta:
        db_table = "events_certificate_settings"
        verbose_name = _("paramètres des attestations")

    def __str__(self) -> str:
        return str(self.edition_id)


class DocumentTemplate(TimeStampedModel):
    """Gabarit d'une nature de pièce (K19) : titre, texte et pied de page FR et EN, à
    variables fermées (``{name}``, ``{edition}``…), et signataire désigné (K18). Sans ligne,
    le gabarit par défaut s'applique, et aucun signataire n'est désigné : rien ne s'émet."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="document_templates",
    )
    nature = models.CharField(_("nature"), max_length=16, choices=DocumentNature.choices)
    title_fr = models.CharField(_("titre (FR)"), max_length=200, blank=True, default="")
    title_en = models.CharField(_("titre (EN)"), max_length=200, blank=True, default="")
    body_fr = models.TextField(_("texte (FR)"), max_length=2000, blank=True, default="")
    body_en = models.TextField(_("texte (EN)"), max_length=2000, blank=True, default="")
    footer_fr = models.CharField(_("pied de page (FR)"), max_length=500, blank=True, default="")
    footer_en = models.CharField(_("pied de page (EN)"), max_length=500, blank=True, default="")
    signatory = models.ForeignKey(
        Signature,
        verbose_name=_("signataire"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="templates",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "nature",
        "title_fr",
        "title_en",
        "body_fr",
        "body_en",
        "footer_fr",
        "footer_en",
        "signatory",
    )

    class Meta:
        db_table = "events_document_template"
        verbose_name = _("gabarit de pièce")
        constraints: ClassVar[list] = [
            models.UniqueConstraint(fields=("edition", "nature"), name="events_template_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.edition_id}:{self.nature}"


class Certificate(TimeStampedModel):
    """Attestation émise (K9, RG-16) : **figée** et en ajout seul ; révocable (motif,
    journal), jamais supprimée.

    - nom, institution et détails (titre de la communication, nombre d'évaluations) figés à
      l'émission ; signataire figé (nom, fonction, empreinte de l'image) ;
    - code de vérification public (128 bits, base32), dans le QR ;
    - PDF privé (règle n° 8) et son empreinte SHA-256 ;
    - ``active_key`` : une attestation non révoquée par (édition, personne, nature, objet).
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="certificates",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("titulaire"),
        on_delete=models.RESTRICT,
        related_name="certificates",
    )
    nature = models.CharField(_("nature"), max_length=16, choices=DocumentNature.choices)
    submission = models.ForeignKey(
        "submissions.Submission",
        verbose_name=_("communication"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="certificates",
    )
    name = models.CharField(_("nom"), max_length=300)
    institution = models.CharField(_("institution"), max_length=255, blank=True, default="")
    details = models.JSONField(_("détails"), default=dict, blank=True)
    verification_code = models.CharField(_("code de vérification"), max_length=32, unique=True)
    storage_name = models.CharField(_("PDF (nom de stockage)"), max_length=64)
    sha256 = models.CharField(_("empreinte du PDF"), max_length=64)
    size = models.PositiveIntegerField(_("taille"))
    signing_mode = models.CharField(_("signature"), max_length=10, choices=SigningMode.choices)
    signatory_name = models.CharField(_("signataire"), max_length=150)
    signatory_title_fr = models.CharField(_("fonction du signataire (FR)"), max_length=200)
    signatory_title_en = models.CharField(
        _("fonction du signataire (EN)"), max_length=200, blank=True, default=""
    )
    signature_sha256 = models.CharField(_("empreinte de l'image de signature"), max_length=64)
    issued_at = models.DateTimeField(_("émise le"))
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("émise à la demande de"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    revoked_at = models.DateTimeField(_("révoquée le"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("révoquée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    revoke_reason = models.CharField(
        _("motif de révocation"), max_length=500, blank=True, default=""
    )
    active_key = models.CharField(
        _("clé de l'attestation active"), max_length=64, null=True, blank=True, unique=True
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "user",
        "nature",
        "submission",
        "sha256",
        "signing_mode",
        "signatory_name",
        "issued_at",
        "revoked_at",
        "revoke_reason",
    )

    class Meta:
        db_table = "events_certificate"
        verbose_name = _("attestation")
        indexes: ClassVar[list] = [
            models.Index(fields=("edition", "nature"), name="events_certificate_nature"),
        ]

    def __str__(self) -> str:
        return f"{self.edition_id}:{self.user_id}:{self.nature}"

    @staticmethod
    def make_active_key(edition_id: int, user_id: int, nature: str, submission_id: int | None):
        return f"{edition_id}:{user_id}:{nature}:{submission_id or 0}"


# --- Lettres d'invitation (K12) ------------------------------------------------------------------


class LetterStatus(models.TextChoices):
    REQUESTED = "requested", _("demandée")
    ISSUED = "issued", _("émise")
    REFUSED = "refused", _("refusée")
    REVOKED = "revoked", _("révoquée")


class InvitationLetter(TimeStampedModel):
    """Lettre d'invitation (visa) demandée par un participant inscrit (K12), instruite par le
    CO (``letters.manage``) : émise (PDF figé, vérifiable comme une attestation) ou refusée
    (motif). Le **numéro de passeport** est effacé à l'anonymisation et 30 jours après la
    fin de l'édition (K14) ; il ne figure jamais au journal.

    ``active_key`` : une demande en cours ou une lettre émise au plus par inscription.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="invitation_letters",
    )
    registration = models.ForeignKey(
        "registrations.Registration",
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="invitation_letters",
    )
    passport_name = models.CharField(_("nom (passeport)"), max_length=200)
    nationality = models.CharField(_("nationalité"), max_length=100)
    passport_number = models.CharField(
        _("numéro de passeport"), max_length=40, blank=True, default=""
    )
    passport_erased_at = models.DateTimeField(_("numéro effacé le"), null=True, blank=True)
    stay_from = models.DateField(_("arrivée"))
    stay_to = models.DateField(_("départ"))
    embassy = models.CharField(_("ambassade ou consulat"), max_length=300)
    status = models.CharField(
        _("statut"), max_length=10, choices=LetterStatus.choices, default=LetterStatus.REQUESTED
    )
    decided_at = models.DateTimeField(_("instruite le"), null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("instruite par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    refuse_reason = models.CharField(_("motif du refus"), max_length=500, blank=True, default="")
    verification_code = models.CharField(
        _("code de vérification"), max_length=32, null=True, blank=True, unique=True
    )
    storage_name = models.CharField(
        _("PDF (nom de stockage)"), max_length=64, blank=True, default=""
    )
    sha256 = models.CharField(_("empreinte du PDF"), max_length=64, blank=True, default="")
    size = models.PositiveIntegerField(_("taille"), default=0)
    signing_mode = models.CharField(
        _("signature"), max_length=10, choices=SigningMode.choices, blank=True, default=""
    )
    signatory_name = models.CharField(_("signataire"), max_length=150, blank=True, default="")
    signatory_title_fr = models.CharField(
        _("fonction du signataire (FR)"), max_length=200, blank=True, default=""
    )
    signatory_title_en = models.CharField(
        _("fonction du signataire (EN)"), max_length=200, blank=True, default=""
    )
    signature_sha256 = models.CharField(
        _("empreinte de l'image de signature"), max_length=64, blank=True, default=""
    )
    issued_at = models.DateTimeField(_("émise le"), null=True, blank=True)
    revoked_at = models.DateTimeField(_("révoquée le"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("révoquée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    revoke_reason = models.CharField(
        _("motif de révocation"), max_length=500, blank=True, default=""
    )
    active_key = models.CharField(
        _("clé de la lettre active"), max_length=32, null=True, blank=True, unique=True
    )

    # Jamais le numéro de passeport (K14).
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "registration",
        "passport_name",
        "nationality",
        "stay_from",
        "stay_to",
        "embassy",
        "status",
        "refuse_reason",
        "sha256",
        "signing_mode",
        "signatory_name",
        "revoke_reason",
    )

    class Meta:
        db_table = "events_invitation_letter"
        verbose_name = _("lettre d'invitation")
        indexes: ClassVar[list] = [
            models.Index(fields=("edition", "status"), name="events_letter_status"),
        ]

    def __str__(self) -> str:
        return f"{self.registration_id}:{self.status}"
