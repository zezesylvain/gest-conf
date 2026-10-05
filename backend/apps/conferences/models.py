"""Conférence, éditions et paramétrage (plan L1 §3.4, M3).

Libellés éditoriaux en colonnes ``_fr`` / ``_en`` (D14) : le français est obligatoire,
l'anglais l'est pour publier. Les autres paramètres arriveront en colonnes typées dans
leur lot (langues des soumissions en L3, seuils en L4, devise en L6...).
"""

from __future__ import annotations

from typing import ClassVar

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.accounts.validators import validate_country
from apps.conferences.validators import validate_edition_code, validate_timezone
from apps.core.models import TimeStampedModel

DEFAULT_TIMEZONE = "Africa/Abidjan"


class Conference(TimeStampedModel):
    """Conférence, créée par commande (D1). ``current_edition`` : migration 0002."""

    slug = models.SlugField(_("identifiant"), max_length=64, unique=True)
    name_fr = models.CharField(_("nom (FR)"), max_length=255)
    name_en = models.CharField(_("nom (EN)"), max_length=255, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    # Édition courante : une clé étrangère évite une unicité conditionnelle (MariaDB, §3.1).
    current_edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition courante"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("slug", "name_fr", "name_en", "current_edition")

    class Meta:
        verbose_name = _("conférence")
        verbose_name_plural = _("conférences")

    def __str__(self) -> str:
        return self.slug


SUBMISSION_LANGUAGES = ("fr", "en")


def default_submission_languages() -> list[str]:
    return list(SUBMISSION_LANGUAGES)


class EditionStatus(models.TextChoices):
    DRAFT = "draft", _("brouillon")
    PUBLISHED = "published", _("publiée")
    ARCHIVED = "archived", _("archivée")


class Edition(TimeStampedModel):
    conference = models.ForeignKey(
        Conference, verbose_name=_("conférence"), on_delete=models.RESTRICT, related_name="editions"
    )
    code = models.CharField(
        _("code"), max_length=12, unique=True, validators=[validate_edition_code]
    )
    slug = models.SlugField(_("identifiant"), max_length=64)
    year = models.PositiveSmallIntegerField(
        _("année"), validators=[MinValueValidator(2000), MaxValueValidator(2100)]
    )
    title_fr = models.CharField(_("titre (FR)"), max_length=255)
    title_en = models.CharField(_("titre (EN)"), max_length=255, blank=True, default="")
    theme_fr = models.CharField(_("thème (FR)"), max_length=500, blank=True, default="")
    theme_en = models.CharField(_("thème (EN)"), max_length=500, blank=True, default="")
    start_date = models.DateField(_("début"), null=True, blank=True)
    end_date = models.DateField(_("fin"), null=True, blank=True)
    venue = models.CharField(_("lieu"), max_length=255, blank=True, default="")
    city = models.CharField(_("ville"), max_length=128, blank=True, default="")
    country = models.CharField(
        _("pays"), max_length=2, blank=True, default="", validators=[validate_country]
    )
    timezone = models.CharField(
        _("fuseau horaire"),
        max_length=64,
        default=DEFAULT_TIMEZONE,
        validators=[validate_timezone],
    )
    double_blind = models.BooleanField(_("double aveugle"), default=True)
    # Langues acceptées pour les soumissions (plan L3, F11 ; Q6) : codes ISO 639-1.
    submission_languages = models.JSONField(
        _("langues des soumissions"), default=default_submission_languages
    )
    reviewers_per_submission = models.PositiveSmallIntegerField(
        _("relecteurs par soumission"),
        default=2,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
    )
    status = models.CharField(
        _("statut"), max_length=10, choices=EditionStatus.choices, default=EditionStatus.DRAFT
    )
    published_at = models.DateTimeField(_("publiée le"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archivée le"), null=True, blank=True)
    # Affiche (lot L2, E7) : image Open Graph et en-tête du portail ; choisie dans les images
    # publiques de l'édition par ``portal.services.set_poster``.
    poster = models.ForeignKey(
        "core.PublicFile",
        verbose_name=_("affiche"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    # Champs de configuration journalisés avant/après (RG-17, B14).
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "slug",
        "year",
        "title_fr",
        "title_en",
        "theme_fr",
        "theme_en",
        "start_date",
        "end_date",
        "venue",
        "city",
        "country",
        "timezone",
        "double_blind",
        "submission_languages",
        "reviewers_per_submission",
        "status",
    )

    class Meta:
        verbose_name = _("édition")
        verbose_name_plural = _("éditions")
        constraints = (
            models.UniqueConstraint(fields=["conference", "slug"], name="conf_edition_slug"),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(start_date__isnull=True)
                | Q(end_date__gte=F("start_date")),
                name="conf_edition_dates_order",
            ),
            models.CheckConstraint(
                condition=Q(reviewers_per_submission__gte=1, reviewers_per_submission__lte=10),
                name="conf_edition_reviewers_range",
            ),
        )
        indexes = (models.Index(fields=["conference", "status"], name="conf_edition_status"),)

    def __str__(self) -> str:
        return self.code

    @property
    def is_archived(self) -> bool:
        return self.status == EditionStatus.ARCHIVED


class Track(TimeStampedModel):
    """Thématique. Pas de président de track en L1 (B5)."""

    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="tracks"
    )
    code = models.SlugField(_("code"), max_length=32)
    name_fr = models.CharField(_("nom (FR)"), max_length=255)
    name_en = models.CharField(_("nom (EN)"), max_length=255, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    is_active = models.BooleanField(_("active"), default=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "name_fr",
        "name_en",
        "description_fr",
        "description_en",
        "position",
        "is_active",
    )

    class Meta:
        verbose_name = _("thématique")
        verbose_name_plural = _("thématiques")
        ordering = ("position", "id")
        constraints = (models.UniqueConstraint(fields=["edition", "code"], name="conf_track_code"),)
        indexes = (models.Index(fields=["edition", "position"], name="conf_track_position"),)

    def __str__(self) -> str:
        return self.code


class FilePolicy(models.TextChoices):
    """Fichier PDF attendu pour un type de communication (plan L3, F1 ; Q5)."""

    NONE = "none", _("aucun fichier")
    OPTIONAL = "optional", _("facultatif")
    REQUIRED = "required", _("obligatoire")


class SubmissionType(TimeStampedModel):
    """Type de communication. Résumé toujours ; fichier PDF selon ``file_policy`` (F1)."""

    edition = models.ForeignKey(
        Edition,
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="submission_types",
    )
    code = models.SlugField(_("code"), max_length=32)
    label_fr = models.CharField(_("libellé (FR)"), max_length=255)
    label_en = models.CharField(_("libellé (EN)"), max_length=255, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    # Null pour les posters (pas de créneau oral).
    default_duration_min = models.PositiveSmallIntegerField(
        _("durée par défaut (min)"), null=True, blank=True
    )
    abstract_max_words = models.PositiveSmallIntegerField(
        _("mots maximum du résumé"),
        default=300,
        validators=[MinValueValidator(50), MaxValueValidator(2000)],
    )
    file_policy = models.CharField(
        _("fichier PDF"), max_length=8, choices=FilePolicy.choices, default=FilePolicy.OPTIONAL
    )
    max_file_mb = models.PositiveSmallIntegerField(
        _("taille maximale du fichier (Mo)"),
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(50)],
    )
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    is_active = models.BooleanField(_("actif"), default=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "label_fr",
        "label_en",
        "description_fr",
        "description_en",
        "default_duration_min",
        "abstract_max_words",
        "file_policy",
        "max_file_mb",
        "position",
        "is_active",
    )

    class Meta:
        verbose_name = _("type de communication")
        verbose_name_plural = _("types de communication")
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="conf_subtype_code"),
            models.CheckConstraint(
                condition=Q(abstract_max_words__gte=50, abstract_max_words__lte=2000),
                name="conf_subtype_words_range",
            ),
            models.CheckConstraint(
                condition=Q(max_file_mb__gte=1, max_file_mb__lte=50),
                name="conf_subtype_file_mb_range",
            ),
        )

    def __str__(self) -> str:
        return self.code


class KeyDateCode(models.TextChoices):
    """Codes réservés, dont le code métier connaît la signification (plan §3.4)."""

    CALL_OPEN = "call_open", _("ouverture de l'appel")
    CALL_CLOSE = "call_close", _("clôture de l'appel")
    REVIEW_DEADLINE = "review_deadline", _("fin des évaluations")
    NOTIFICATION = "notification", _("notification des décisions")
    CAMERA_READY = "camera_ready", _("version définitive")
    REGISTRATION_OPEN = "registration_open", _("ouverture des inscriptions")
    EARLY_BIRD_END = "early_bird_end", _("fin du tarif préférentiel")
    REGISTRATION_CLOSE = "registration_close", _("clôture des inscriptions")


# Chaînes d'ordre contrôlé (« a < b » strict pour le premier maillon, puis « ≤ »).
KEY_DATE_CHAINS: tuple[tuple[str, ...], ...] = (
    ("call_open", "call_close", "review_deadline", "notification", "camera_ready"),
    ("registration_open", "early_bird_end", "registration_close"),
)


class KeyDate(TimeStampedModel):
    """Date clé, stockée en UTC ; saisie à l'heure de l'édition (D13)."""

    edition = models.ForeignKey(
        Edition, verbose_name=_("édition"), on_delete=models.RESTRICT, related_name="key_dates"
    )
    code = models.SlugField(_("code"), max_length=32)
    at = models.DateTimeField(_("date (UTC)"))
    # Libellés obligatoires pour un code libre ; facultatifs pour un code réservé.
    label_fr = models.CharField(_("libellé (FR)"), max_length=255, blank=True, default="")
    label_en = models.CharField(_("libellé (EN)"), max_length=255, blank=True, default="")
    is_public = models.BooleanField(_("publique"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "code",
        "at",
        "label_fr",
        "label_en",
        "is_public",
        "position",
    )

    class Meta:
        verbose_name = _("date clé")
        verbose_name_plural = _("dates clés")
        ordering = ("at", "position", "id")
        constraints = (
            models.UniqueConstraint(fields=["edition", "code"], name="conf_keydate_code"),
        )
        indexes = (models.Index(fields=["edition", "at"], name="conf_keydate_at"),)

    def __str__(self) -> str:
        return self.code

    @property
    def is_reserved(self) -> bool:
        return self.code in KeyDateCode.values
