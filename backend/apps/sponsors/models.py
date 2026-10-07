"""Partenaires de l'édition (plan L8 §3, N5 ; étude M13, §8.2 ``sponsor``).

Niveaux (publics), fiches (partie publique et partie privée : contact, contribution, note),
contreparties suivies une à une. Écrits par ``apps.sponsors.services`` seul.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.registrations.models import money_field


class LogoSize(models.TextChoices):
    """Taille des logos d'un niveau sur la page « Partenaires » du portail."""

    SMALL = "small", _("petite")
    MEDIUM = "medium", _("moyenne")
    LARGE = "large", _("grande")


class SponsorLevel(TimeStampedModel):
    """Niveau de partenariat (platine, or…), public : nom, contreparties, taille du logo."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="sponsor_levels",
    )
    name_fr = models.CharField(_("nom (FR)"), max_length=100)
    name_en = models.CharField(_("nom (EN)"), max_length=100, blank=True, default="")
    amount = money_field(_("montant indicatif"), null=True, blank=True)
    benefits_fr = models.TextField(_("contreparties (FR)"), blank=True, default="")
    benefits_en = models.TextField(_("contreparties (EN)"), blank=True, default="")
    logo_size = models.CharField(
        _("taille du logo"), max_length=8, choices=LogoSize.choices, default=LogoSize.MEDIUM
    )
    position = models.PositiveIntegerField(_("ordre"), default=0)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "name_fr",
        "name_en",
        "amount",
        "benefits_fr",
        "benefits_en",
        "logo_size",
        "position",
    )

    class Meta:
        verbose_name = _("niveau de partenariat")
        verbose_name_plural = _("niveaux de partenariat")
        ordering = ("edition", "position", "id")
        constraints = (
            models.CheckConstraint(
                condition=Q(amount__isnull=True) | Q(amount__gte=0), name="spo_level_amount_pos"
            ),
        )

    def __str__(self) -> str:
        return self.name_fr


class SponsorStatus(models.TextChoices):
    PROSPECT = "prospect", _("prospect")
    AGREED = "agreed", _("accord conclu")
    RECEIVED = "received", _("contribution reçue")
    DECLINED = "declined", _("refus")


class Sponsor(TimeStampedModel):
    """Partenaire (N5). Publics : nom, niveau, logo, site, présentations, s'il est publié.
    Privés : contact (jamais publié ni journalisé en clair), contribution, statut, note."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="sponsors",
    )
    name = models.CharField(_("nom"), max_length=150)
    level = models.ForeignKey(
        SponsorLevel,
        verbose_name=_("niveau"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="sponsors",
    )
    logo = models.ForeignKey(
        "core.PublicFile",
        verbose_name=_("logo"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    website = models.URLField(_("site"), max_length=300, blank=True, default="")
    description_fr = models.TextField(_("présentation (FR)"), blank=True, default="")
    description_en = models.TextField(_("présentation (EN)"), blank=True, default="")
    published = models.BooleanField(_("publié sur le portail"), default=False)
    position = models.PositiveIntegerField(_("ordre"), default=0)
    contact_name = models.CharField(_("contact"), max_length=150, blank=True, default="")
    contact_email = models.EmailField(_("adresse du contact"), blank=True, default="")
    contact_phone = models.CharField(
        _("téléphone du contact"), max_length=40, blank=True, default=""
    )
    status = models.CharField(
        _("statut"), max_length=10, choices=SponsorStatus.choices, default=SponsorStatus.PROSPECT
    )
    agreed_amount = money_field(_("contribution convenue"), null=True, blank=True)
    received_amount = money_field(_("montant reçu"), null=True, blank=True)
    received_on = models.DateField(_("reçu le"), null=True, blank=True)
    note = models.TextField(_("note interne"), blank=True, default="")

    PUBLIC_FIELDS: ClassVar[tuple[str, ...]] = (
        "name",
        "level",
        "website",
        "description_fr",
        "description_en",
        "published",
        "position",
    )
    PRIVATE_FIELDS: ClassVar[tuple[str, ...]] = (
        "status",
        "agreed_amount",
        "received_amount",
        "received_on",
        "note",
    )
    CONTACT_FIELDS: ClassVar[tuple[str, ...]] = ("contact_name", "contact_email", "contact_phone")

    class Meta:
        verbose_name = _("partenaire")
        verbose_name_plural = _("partenaires")
        ordering = ("edition", "position", "id")
        constraints = (
            models.CheckConstraint(
                condition=Q(agreed_amount__isnull=True) | Q(agreed_amount__gte=0),
                name="spo_agreed_pos",
            ),
            models.CheckConstraint(
                condition=Q(received_amount__isnull=True) | Q(received_amount__gte=0),
                name="spo_received_pos",
            ),
        )

    def __str__(self) -> str:
        return self.name


class SponsorBenefit(TimeStampedModel):
    """Contrepartie due à un partenaire, cochée à sa livraison (N5)."""

    sponsor = models.ForeignKey(
        Sponsor, verbose_name=_("partenaire"), on_delete=models.CASCADE, related_name="benefits"
    )
    label = models.CharField(_("contrepartie"), max_length=200)
    delivered_on = models.DateField(_("livrée le"), null=True, blank=True)
    position = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("contrepartie")
        verbose_name_plural = _("contreparties")
        ordering = ("sponsor", "position", "id")
