"""Paiements, factures et avoirs (plan L6 §3 ; étude §8.2, §8.3, RG-14, RG-15).

- **Paiement** : une tentative par ligne, en ligne (fournisseur) ou manuelle (virement, sur
  place). Une inscription n'est confirmée que par un paiement ``succeeded`` (notification
  vérifiée **et** statut interrogé côté serveur, RG-15) ou validé à la main par le CO
  « finances » (J7). Aucune donnée de carte (règle n° 7).
- **Notification** : chaque appel reçu du fournisseur, en ajout seul, avec le résultat de sa
  vérification ; jamais le jeton reçu ni de donnée de carte.
- **Pièce** (facture, avoir, pro forma) : en ajout seul, numérotée sans trou par série et par
  année (``core.Counter``), PDF hors racine web et empreinte SHA-256 (RG-14, J8). Les factures
  et avoirs sont conservés à l'anonymisation du participant (J14).
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyModel, TimeStampedModel
from apps.core.money import Currency
from apps.registrations.models import PaymentMethod, money_field

# --- Mentions de facturation (J8, Q8) -------------------------------------------------------


class BillingProfile(TimeStampedModel):
    """Mentions de facturation de l'édition (Q8) : émetteur, identifiants, TVA éventuelle,
    pied de page, coordonnées bancaires de la pro forma, préfixes des séries.

    Tant que la raison sociale et l'adresse manquent, **aucune facture ne s'émet** (J8) : les
    paiements restent possibles, les factures sont émises ensuite."""

    edition = models.OneToOneField(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="billing_profile",
    )
    legal_name = models.CharField(_("raison sociale"), max_length=255, blank=True, default="")
    address = models.TextField(_("adresse"), blank=True, default="")
    tax_identifiers = models.TextField(_("identifiants (registre, fiscal)"), blank=True, default="")
    vat_rate = models.DecimalField(
        _("taux de TVA (%)"),
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    vat_note = models.CharField(_("mention de TVA"), max_length=255, blank=True, default="")
    footer = models.TextField(_("pied de page"), blank=True, default="")
    bank_details = models.TextField(_("coordonnées bancaires"), blank=True, default="")
    invoice_prefix = models.CharField(_("préfixe des factures"), max_length=8, default="F")
    credit_note_prefix = models.CharField(_("préfixe des avoirs"), max_length=8, default="AV")
    proforma_prefix = models.CharField(_("préfixe des pro forma"), max_length=8, default="PF")

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "legal_name",
        "address",
        "tax_identifiers",
        "vat_rate",
        "vat_note",
        "footer",
        "bank_details",
        "invoice_prefix",
        "credit_note_prefix",
        "proforma_prefix",
    )

    class Meta:
        verbose_name = _("mentions de facturation")
        verbose_name_plural = _("mentions de facturation")

    def __str__(self) -> str:
        return str(self.edition_id)

    @property
    def is_complete(self) -> bool:
        return bool(self.legal_name.strip() and self.address.strip())


# --- Paiements (J6, J7, RG-15) ----------------------------------------------------------------


class Provider(models.TextChoices):
    MANUAL = "manual", _("paiement manuel")
    FAKE = "fake", _("fournisseur factice")
    CINETPAY = "cinetpay", _("CinetPay")


class PaymentStatus(models.TextChoices):
    INITIATED = "initiated", _("initié")
    PENDING = "pending", _("en cours")
    SUCCEEDED = "succeeded", _("réussi")
    FAILED = "failed", _("échoué")
    CANCELLED = "cancelled", _("abandonné")


class Payment(TimeStampedModel):
    """Tentative de paiement d'une inscription.

    - ``reference`` : notre identifiant de transaction, unique par fournisseur (30 caractères
      au plus pour CinetPay, une référence par tentative, bilan de L6.0) ;
    - ``provider_reference`` : identifiant du fournisseur, ou référence du virement ;
    - ``notify_token_hash`` : empreinte SHA-256 du jeton de notification remis par le
      fournisseur à l'initiation (le jeton lui-même n'est jamais conservé) ;
    - paiement manuel : ``recorded_by`` et ``received_on``, validés avec réauthentification.
    """

    registration = models.ForeignKey(
        "registrations.Registration",
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="payments",
    )
    provider = models.CharField(_("fournisseur"), max_length=16, choices=Provider.choices)
    method = models.CharField(_("moyen"), max_length=10, choices=PaymentMethod.choices)
    reference = models.CharField(_("référence"), max_length=30)
    provider_reference = models.CharField(
        _("référence du fournisseur"), max_length=64, blank=True, default=""
    )
    amount = money_field(_("montant"))
    currency = models.CharField(_("devise"), max_length=3, choices=Currency.choices)
    status = models.CharField(
        _("statut"), max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.INITIATED
    )
    provider_status = models.CharField(
        _("dernier statut du fournisseur"), max_length=32, blank=True, default=""
    )
    notify_token_hash = models.CharField(
        _("empreinte du jeton de notification"), max_length=64, blank=True, default=""
    )
    completed_at = models.DateTimeField(_("terminé le"), null=True, blank=True)
    last_checked_at = models.DateTimeField(_("dernière interrogation"), null=True, blank=True)
    received_on = models.DateField(_("reçu le"), null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("validé par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    note = models.CharField(_("note"), max_length=255, blank=True, default="")

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "provider",
        "method",
        "reference",
        "provider_reference",
        "amount",
        "currency",
        "status",
        "provider_status",
        "received_on",
        "note",
    )

    class Meta:
        verbose_name = _("paiement")
        verbose_name_plural = _("paiements")
        ordering = ("registration", "-created_at", "id")
        constraints = (
            models.UniqueConstraint(fields=["provider", "reference"], name="pay_reference"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="pay_amount_positive"),
        )
        indexes = (models.Index(fields=["status", "provider"], name="pay_status_provider"),)

    def __str__(self) -> str:
        return f"{self.provider}:{self.reference}"


class PaymentNotification(AppendOnlyModel):
    """Notification reçue d'un fournisseur (J6) : référence annoncée, résultat de la
    vérification, champs reçus **en liste blanche** (jamais le jeton, aucune donnée de carte),
    issue du traitement."""

    provider = models.CharField(_("fournisseur"), max_length=16, choices=Provider.choices)
    reference = models.CharField(_("référence annoncée"), max_length=64, blank=True, default="")
    payment = models.ForeignKey(
        Payment,
        verbose_name=_("paiement"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="notifications",
    )
    received_at = models.DateTimeField(_("reçue le"))
    token_valid = models.BooleanField(_("jeton valide"), default=False)
    outcome = models.CharField(_("issue"), max_length=32)
    body = models.JSONField(_("champs reçus"), default=dict)

    class Meta:
        verbose_name = _("notification de paiement")
        verbose_name_plural = _("notifications de paiement")
        ordering = ("-received_at", "-id")
        indexes = (models.Index(fields=["provider", "reference"], name="pay_notification_ref"),)

    def __str__(self) -> str:
        return f"{self.provider}:{self.reference}:{self.outcome}"


# --- Factures, avoirs, pro forma (RG-14, J8, J9) ----------------------------------------------


class DocumentKind(models.TextChoices):
    INVOICE = "invoice", _("facture")
    CREDIT_NOTE = "credit_note", _("avoir")
    PROFORMA = "proforma", _("pro forma")


class BillingDocument(AppendOnlyModel):
    """Facture, avoir ou pro forma : pièce immuable (RG-14).

    - numérotation sans trou par (édition, nature, année) : ``sequence`` vient de
      ``core.Counter`` dans la transaction d'émission ; ``number`` est son affichage
      (« F2027-00001 ») ;
    - ``issuer`` et ``customer`` : mentions et identité **figées** à l'émission ;
    - ``original`` : facture d'origine d'un avoir ;
    - PDF stocké hors racine web (``storage_name``), empreinte SHA-256 contrôlée par le
      contrôle d'intégrité.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="billing_documents",
    )
    kind = models.CharField(_("nature"), max_length=12, choices=DocumentKind.choices)
    year = models.PositiveSmallIntegerField(_("année"))
    sequence = models.PositiveIntegerField(_("rang dans la série"))
    number = models.CharField(_("numéro"), max_length=32)
    registration = models.ForeignKey(
        "registrations.Registration",
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="billing_documents",
    )
    original = models.ForeignKey(
        "self",
        verbose_name=_("facture d'origine"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="credit_notes",
    )
    payment = models.ForeignKey(
        Payment,
        verbose_name=_("paiement"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="billing_documents",
    )
    amount = money_field(_("montant"))
    currency = models.CharField(_("devise"), max_length=3, choices=Currency.choices)
    lines = models.JSONField(_("lignes"), default=list)
    issuer = models.JSONField(_("émetteur (mentions figées)"), default=dict)
    customer = models.JSONField(_("client (identité figée)"), default=dict)
    storage_name = models.CharField(_("fichier"), max_length=64)
    sha256 = models.CharField(_("empreinte SHA-256"), max_length=64)
    size = models.PositiveIntegerField(_("taille"))
    issued_at = models.DateTimeField(_("émise le"))
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("émise par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("pièce de facturation")
        verbose_name_plural = _("pièces de facturation")
        ordering = ("edition", "kind", "year", "sequence")
        constraints = (
            models.UniqueConstraint(
                fields=["edition", "kind", "year", "sequence"], name="pay_document_sequence"
            ),
            models.UniqueConstraint(fields=["edition", "number"], name="pay_document_number"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="pay_document_amount"),
            models.CheckConstraint(
                condition=Q(kind="credit_note", original__isnull=False)
                | (~Q(kind="credit_note") & Q(original__isnull=True)),
                name="pay_document_original",
            ),
        )

    def __str__(self) -> str:
        return self.number


class Refund(TimeStampedModel):
    """Remboursement fait **hors plateforme** (tableau de bord de l'agrégateur, virement) et
    enregistré par le CO « finances » (J9) ; il accompagne l'avoir."""

    registration = models.ForeignKey(
        "registrations.Registration",
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="refunds",
    )
    credit_note = models.OneToOneField(
        BillingDocument,
        verbose_name=_("avoir"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="refund",
    )
    amount = money_field(_("montant"))
    currency = models.CharField(_("devise"), max_length=3, choices=Currency.choices)
    method = models.CharField(_("moyen"), max_length=64)
    reference = models.CharField(_("référence"), max_length=64, blank=True, default="")
    refunded_on = models.DateField(_("remboursé le"))
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("enregistré par"),
        on_delete=models.RESTRICT,
        related_name="+",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "amount",
        "currency",
        "method",
        "reference",
        "refunded_on",
    )

    class Meta:
        verbose_name = _("remboursement")
        verbose_name_plural = _("remboursements")
        constraints = (models.CheckConstraint(condition=Q(amount__gt=0), name="pay_refund_amount"),)

    def __str__(self) -> str:
        return f"{self.registration_id}:{self.amount}"
