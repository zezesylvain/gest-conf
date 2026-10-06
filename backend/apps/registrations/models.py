"""Inscriptions des participants (plan L6 §3 ; étude M9, §5.3, §8.2 « Inscriptions »).

Une inscription par personne et par édition (J5). Son **prix est figé à la commande** :
lignes (inscription, options, remise), total et devise sont calculés par le serveur seul et
recopiés ici ; les tarifs peuvent ensuite changer sans effet sur elle. Son statut ne change que
par ``apps.registrations.workflow`` (règle n° 4 transposée, J5). Les paiements, factures et
avoirs sont dans ``apps.payments``.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyModel, TimeStampedModel
from apps.core.money import DECIMAL_PLACES, MAX_DIGITS, Currency


def money_field(verbose_name, **kwargs) -> models.DecimalField:
    return models.DecimalField(
        verbose_name, max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, **kwargs
    )


class Period(models.TextChoices):
    """Période tarifaire (J2), déduite des dates clés de l'édition : préférentiel jusqu'à
    ``early_bird_end``, normal jusqu'à ``registration_close``, puis sur place."""

    EARLY = "early", _("préférentiel")
    REGULAR = "regular", _("normal")
    ONSITE = "onsite", _("sur place")


class Zone(models.TextChoices):
    """Zone tarifaire (J2), d'après le pays du profil : « local » si le pays figure parmi les
    pays locaux de l'édition, sinon « international »."""

    LOCAL = "local", _("local")
    INTERNATIONAL = "international", _("international")


class PaymentMethod(models.TextChoices):
    """Moyen de paiement choisi à la commande (J6, J7) ; ``free`` : montant nul ;
    ``waiver`` : gratuité accordée par le CO (J4)."""

    ONLINE = "online", _("paiement en ligne")
    TRANSFER = "transfer", _("virement (bon de commande)")
    ONSITE = "onsite", _("sur place")
    FREE = "free", _("aucun paiement (montant nul)")
    WAIVER = "waiver", _("gratuité accordée")


class LineKind(models.TextChoices):
    """Nature d'une ligne figée d'une inscription ou d'une pièce."""

    REGISTRATION = "registration", _("inscription")
    OPTION = "option", _("option")
    DISCOUNT = "discount", _("remise")


# --- Paramètres de l'édition (J2, J5, J9) -----------------------------------------------------


class RegistrationSettings(TimeStampedModel):
    """Paramètres des inscriptions d'une édition, créés à la première lecture.

    - devise (une par édition, J2), figée dès la première inscription ;
    - pays « locaux » (vide : pays de l'édition) ;
    - moyens de paiement proposés et échéances (J5) ;
    - règles d'annulation (J9) : date limite pour le participant, part remboursée avant et
      après cette date.
    """

    edition = models.OneToOneField(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="registration_settings",
    )
    currency = models.CharField(
        _("devise"), max_length=3, choices=Currency.choices, default=Currency.XOF
    )
    local_countries = models.JSONField(_("pays locaux"), default=list, blank=True)
    online_enabled = models.BooleanField(_("paiement en ligne proposé"), default=False)
    transfer_enabled = models.BooleanField(_("virement proposé"), default=True)
    onsite_enabled = models.BooleanField(_("paiement sur place proposé"), default=True)
    online_deadline_hours = models.PositiveSmallIntegerField(
        _("délai de paiement en ligne (heures)"),
        default=72,
        validators=[MinValueValidator(1), MaxValueValidator(720)],
    )
    transfer_deadline_days = models.PositiveSmallIntegerField(
        _("délai de paiement par virement (jours)"),
        default=30,
        validators=[MinValueValidator(1), MaxValueValidator(180)],
    )
    cancellation_deadline = models.DateTimeField(
        _("annulation par le participant jusqu'au (UTC)"), null=True, blank=True
    )
    refund_percent_before = models.PositiveSmallIntegerField(
        _("part remboursée avant la date limite (%)"),
        default=100,
        validators=[MaxValueValidator(100)],
    )
    refund_percent_after = models.PositiveSmallIntegerField(
        _("part remboursée après la date limite (%)"),
        default=0,
        validators=[MaxValueValidator(100)],
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "currency",
        "local_countries",
        "online_enabled",
        "transfer_enabled",
        "onsite_enabled",
        "online_deadline_hours",
        "transfer_deadline_days",
        "cancellation_deadline",
        "refund_percent_before",
        "refund_percent_after",
    )

    class Meta:
        verbose_name = _("paramètres des inscriptions")
        verbose_name_plural = _("paramètres des inscriptions")
        constraints = (
            models.CheckConstraint(
                condition=Q(refund_percent_before__lte=100, refund_percent_after__lte=100),
                name="reg_settings_refund_range",
            ),
        )

    def __str__(self) -> str:
        return str(self.edition_id)


# --- Catalogue : catégories, tarifs, options, codes promo (J2 à J4) -------------------------


class RegistrationCategory(TimeStampedModel):
    """Catégorie d'inscription (étudiant, participant, intervenant invité…), liste éditable
    par édition. Une catégorie utilisée ne se supprime pas : elle se désactive."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="registration_categories",
    )
    code = models.SlugField(_("code"), max_length=32)
    label_fr = models.CharField(_("libellé (FR)"), max_length=150)
    label_en = models.CharField(_("libellé (EN)"), max_length=150, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    requires_proof = models.BooleanField(_("justificatif demandé"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "label_fr",
        "label_en",
        "requires_proof",
        "is_active",
        "position",
    )

    class Meta:
        verbose_name = _("catégorie d'inscription")
        verbose_name_plural = _("catégories d'inscription")
        ordering = ("edition", "position", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="reg_category_code"),
        )

    def __str__(self) -> str:
        return self.code


class Fee(TimeStampedModel):
    """Tarif d'une catégorie pour une période et une zone (J2). Un montant nul vaut
    gratuité ; une combinaison absente n'est pas proposée."""

    category = models.ForeignKey(
        RegistrationCategory,
        verbose_name=_("catégorie"),
        on_delete=models.RESTRICT,
        related_name="fees",
    )
    period = models.CharField(_("période"), max_length=8, choices=Period.choices)
    zone = models.CharField(_("zone"), max_length=16, choices=Zone.choices)
    amount = money_field(_("montant"))

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("period", "zone", "amount")

    class Meta:
        verbose_name = _("tarif")
        verbose_name_plural = _("tarifs")
        constraints = (
            models.UniqueConstraint(fields=["category", "period", "zone"], name="reg_fee_unique"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="reg_fee_amount_positive"),
        )

    def __str__(self) -> str:
        return f"{self.category_id}:{self.period}:{self.zone}"


class RegistrationOption(TimeStampedModel):
    """Article facultatif (atelier, dîner, visite) : prix par zone, **quota** de places
    (nul : illimité) et catégories autorisées (aucune : toutes), J3.

    ``reserved`` : places tenues par les inscriptions en attente ou confirmées, modifié sous
    verrou de ligne par le service de commande, recoupé par le contrôle d'intégrité."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="registration_options",
    )
    code = models.SlugField(_("code"), max_length=32)
    label_fr = models.CharField(_("libellé (FR)"), max_length=150)
    label_en = models.CharField(_("libellé (EN)"), max_length=150, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    price_local = money_field(_("prix (local)"), default=0)
    price_international = money_field(_("prix (international)"), default=0)
    quota = models.PositiveIntegerField(_("places"), null=True, blank=True)
    reserved = models.PositiveIntegerField(_("places réservées"), default=0)
    categories = models.ManyToManyField(
        RegistrationCategory,
        verbose_name=_("catégories autorisées"),
        blank=True,
        related_name="+",
    )
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "label_fr",
        "label_en",
        "price_local",
        "price_international",
        "quota",
        "is_active",
        "position",
    )

    class Meta:
        verbose_name = _("option d'inscription")
        verbose_name_plural = _("options d'inscription")
        ordering = ("edition", "position", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="reg_option_code"),
            models.CheckConstraint(
                condition=Q(price_local__gte=0, price_international__gte=0),
                name="reg_option_price_positive",
            ),
            models.CheckConstraint(
                condition=Q(quota__isnull=True) | Q(reserved__lte=F("quota")),
                name="reg_option_quota",
            ),
        )

    def __str__(self) -> str:
        return self.code


class DiscountKind(models.TextChoices):
    PERCENT = "percent", _("pourcentage")
    AMOUNT = "amount", _("montant")


class DiscountScope(models.TextChoices):
    REGISTRATION = "registration", _("inscription seule")
    ALL = "all", _("inscription et options")


class PromoCode(TimeStampedModel):
    """Code promo (J4) : pourcentage ou montant, sur l'inscription seule ou avec les options,
    catégories visées (aucune : toutes), utilisations maximales, date limite.

    Code enregistré en majuscules : unique par édition sans tenir compte de la casse. Une
    utilisation est **réservée** à la commande (``reserved_uses``) puis **consommée** à la
    confirmation (``consumed_uses``), sous verrou de ligne."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="promo_codes",
    )
    code = models.CharField(_("code"), max_length=32)
    kind = models.CharField(_("type de remise"), max_length=8, choices=DiscountKind.choices)
    value = money_field(_("valeur"))
    scope = models.CharField(
        _("portée"),
        max_length=16,
        choices=DiscountScope.choices,
        default=DiscountScope.REGISTRATION,
    )
    categories = models.ManyToManyField(
        RegistrationCategory, verbose_name=_("catégories visées"), blank=True, related_name="+"
    )
    max_uses = models.PositiveIntegerField(_("utilisations maximales"), null=True, blank=True)
    reserved_uses = models.PositiveIntegerField(_("utilisations réservées"), default=0)
    consumed_uses = models.PositiveIntegerField(_("utilisations consommées"), default=0)
    valid_until = models.DateTimeField(_("valable jusqu'au (UTC)"), null=True, blank=True)
    is_active = models.BooleanField(_("actif"), default=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "kind",
        "value",
        "scope",
        "max_uses",
        "valid_until",
        "is_active",
    )

    class Meta:
        verbose_name = _("code promo")
        verbose_name_plural = _("codes promo")
        ordering = ("edition", "code")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="reg_promo_code"),
            models.CheckConstraint(condition=Q(value__gt=0), name="reg_promo_value_positive"),
            models.CheckConstraint(
                condition=~Q(kind="percent") | Q(value__lte=100), name="reg_promo_percent_range"
            ),
            models.CheckConstraint(
                condition=Q(max_uses__isnull=True)
                | Q(max_uses__gte=F("reserved_uses") + F("consumed_uses")),
                name="reg_promo_uses",
            ),
        )

    def __str__(self) -> str:
        return self.code


# --- Inscriptions (J5) ----------------------------------------------------------------------


class RegistrationStatus(models.TextChoices):
    PENDING = "pending", _("en attente de paiement")
    CONFIRMED = "confirmed", _("confirmée")
    CANCELLED = "cancelled", _("annulée")
    EXPIRED = "expired", _("expirée")


ACTIVE_STATUSES = (RegistrationStatus.PENDING, RegistrationStatus.CONFIRMED)


class Registration(TimeStampedModel):
    """Inscription d'une personne à une édition (J5).

    - ``lines`` : lignes figées à la commande (``kind`` : ``registration``, ``option`` ou
      ``discount`` ; ``code``, libellés FR et EN, ``amount`` en chaîne décimale) ; ``total``
      est leur somme, dans ``currency`` ;
    - ``options`` : options réservées (quota libéré à l'expiration ou à l'annulation) ;
    - ``active_key`` : renseignée tant que l'inscription est en attente ou confirmée, d'où
      une seule inscription active par (édition, personne) sans unicité conditionnelle ;
    - ``qr_token`` : jeton non devinable, attribué à la confirmation, retiré à l'annulation
      (J11, check-in en L7) ;
    - identité de facturation (nom, organisme, adresse), modifiable jusqu'à la facture, qui
      la fige.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="registrations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("participant"),
        on_delete=models.RESTRICT,
        related_name="registrations",
    )
    category = models.ForeignKey(
        RegistrationCategory,
        verbose_name=_("catégorie"),
        on_delete=models.RESTRICT,
        related_name="registrations",
    )
    status = models.CharField(
        _("statut"),
        max_length=10,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.PENDING,
    )
    period = models.CharField(_("période"), max_length=8, choices=Period.choices)
    zone = models.CharField(_("zone"), max_length=16, choices=Zone.choices)
    method = models.CharField(_("moyen de paiement"), max_length=10, choices=PaymentMethod.choices)
    lines = models.JSONField(_("lignes"), default=list)
    total = money_field(_("total"))
    currency = models.CharField(_("devise"), max_length=3, choices=Currency.choices)
    options = models.ManyToManyField(
        RegistrationOption, verbose_name=_("options"), blank=True, related_name="registrations"
    )
    promo_code = models.ForeignKey(
        PromoCode,
        verbose_name=_("code promo"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="registrations",
    )
    due_at = models.DateTimeField(_("échéance de paiement"), null=True, blank=True)
    confirmed_at = models.DateTimeField(_("confirmée le"), null=True, blank=True)
    closed_at = models.DateTimeField(_("annulée ou expirée le"), null=True, blank=True)
    billing_name = models.CharField(_("nom de facturation"), max_length=255, blank=True, default="")
    billing_organization = models.CharField(
        _("organisme de facturation"), max_length=255, blank=True, default=""
    )
    billing_address = models.TextField(_("adresse de facturation"), blank=True, default="")
    qr_token = models.CharField(_("jeton QR"), max_length=64, null=True, blank=True, unique=True)
    active_key = models.CharField(
        _("clé d'unicité active"), max_length=64, null=True, blank=True, unique=True
    )

    # Le jeton QR n'est jamais journalisé.
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "status",
        "category",
        "period",
        "zone",
        "method",
        "total",
        "currency",
        "due_at",
        "billing_name",
        "billing_organization",
        "billing_address",
    )

    class Meta:
        verbose_name = _("inscription")
        verbose_name_plural = _("inscriptions")
        ordering = ("edition", "-created_at", "id")
        constraints = (
            models.CheckConstraint(condition=Q(total__gte=0), name="reg_registration_total"),
            # Clé active si et seulement si l'inscription est en attente ou confirmée.
            models.CheckConstraint(
                condition=Q(status__in=ACTIVE_STATUSES, active_key__isnull=False)
                | (~Q(status__in=ACTIVE_STATUSES) & Q(active_key__isnull=True)),
                name="reg_registration_active_key",
            ),
            # Jeton QR seulement sur une inscription confirmée (J11).
            models.CheckConstraint(
                condition=Q(qr_token__isnull=True) | Q(status=RegistrationStatus.CONFIRMED),
                name="reg_registration_qr_confirmed",
            ),
        )
        indexes = (
            models.Index(fields=["edition", "status"], name="reg_registration_status"),
            models.Index(fields=["status", "due_at"], name="reg_registration_due"),
        )

    def __str__(self) -> str:
        return f"{self.edition_id}:{self.user_id}:{self.status}"

    @staticmethod
    def make_active_key(edition_id: int, user_id: int) -> str:
        return f"{edition_id}:{user_id}"


class RegistrationStatusHistory(AppendOnlyModel):
    """Historique des statuts d'une inscription (J5), en ajout seul, écrit par le workflow."""

    registration = models.ForeignKey(
        Registration,
        verbose_name=_("inscription"),
        on_delete=models.RESTRICT,
        related_name="history",
    )
    from_status = models.CharField(
        _("statut de départ"), max_length=10, choices=RegistrationStatus.choices, blank=True
    )
    to_status = models.CharField(
        _("statut d'arrivée"), max_length=10, choices=RegistrationStatus.choices
    )
    at = models.DateTimeField(_("date du changement"))
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("auteur du changement"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    actor_label = models.CharField(_("acteur (commande ou tâche)"), max_length=64, blank=True)
    reason = models.TextField(_("motif"), blank=True, default="")

    class Meta:
        verbose_name = _("historique d'une inscription")
        verbose_name_plural = _("historiques des inscriptions")
        ordering = ("registration", "at", "id")

    def __str__(self) -> str:
        return f"{self.registration_id}:{self.from_status}->{self.to_status}"
