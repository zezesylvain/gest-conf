"""Programme de l'édition (plan L5 §3 ; étude M7, §5.4, §8.2 « Programme »).

Structure (I2) : édition → jours (dates de l'édition, sans table) → sessions → créneaux. Les
débuts et fins des créneaux sont **calculés** par le service de planification (I3) à partir du
début de la session, des durées et des tampons (RG-13) ; ils sont stockés pour les recherches
de conflits (RG-12). MariaDB n'offrant pas de contrainte d'exclusion de plages, ces conflits
sont contrôlés par le service, sous verrou, et par le contrôle d'intégrité (§8.2).

Le **brouillon** (salles, sessions, créneaux, rôles de séance) n'est jamais servi hors de la
gestion ; le public et « Mon passage » lisent la dernière publication (instantané, I6).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyModel, TimeStampedModel

# --- Salles (I9) ---------------------------------------------------------------------------


class Equipment(models.TextChoices):
    """Équipements d'une salle : liste fermée (I9), complétée par une note libre."""

    PROJECTOR = "projector", _("vidéoprojecteur")
    MICROPHONE = "microphone", _("micro")
    SOUND_SYSTEM = "sound_system", _("sonorisation")
    COMPUTER = "computer", _("ordinateur")
    WHITEBOARD = "whiteboard", _("tableau")
    INTERPRETATION = "interpretation", _("interprétation")
    RECORDING = "recording", _("enregistrement")
    WIFI = "wifi", _("wifi")


class Room(TimeStampedModel):
    """Salle d'une édition. Une salle utilisée ne se supprime pas : elle se désactive."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="rooms",
    )
    name = models.CharField(_("nom"), max_length=150)
    capacity = models.PositiveIntegerField(
        _("capacité"), null=True, blank=True, validators=[MaxValueValidator(100_000)]
    )
    equipment = models.JSONField(_("équipements"), default=list, blank=True)
    note = models.TextField(_("note sur l'équipement"), blank=True, default="")
    is_accessible = models.BooleanField(_("accessible"), default=False)
    access_note = models.CharField(_("indications d'accès"), max_length=255, blank=True, default="")
    is_active = models.BooleanField(_("active"), default=True)
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "name",
        "capacity",
        "equipment",
        "note",
        "is_accessible",
        "access_note",
        "is_active",
        "position",
    )

    class Meta:
        verbose_name = _("salle")
        verbose_name_plural = _("salles")
        ordering = ("edition", "position", "name", "id")
        constraints = (models.UniqueConstraint(fields=["edition", "name"], name="prog_room_name"),)

    def __str__(self) -> str:
        return self.name


# --- Sessions (I2) -------------------------------------------------------------------------


class SessionKind(models.TextChoices):
    """Types de session : catalogue fermé (I2) ; liste paramétrable par édition : P2."""

    OPENING = "opening", _("ouverture")
    KEYNOTE = "keynote", _("conférence plénière")
    PARALLEL = "parallel", _("session parallèle")
    POSTER = "poster", _("session posters")
    WORKSHOP = "workshop", _("atelier")
    TUTORIAL = "tutorial", _("tutoriel")
    ROUND_TABLE = "round_table", _("table ronde")
    ASSEMBLY = "assembly", _("assemblée ou réunion")
    BREAK = "break", _("pause")
    MEAL = "meal", _("repas")
    SOCIAL = "social", _("activité sociale")
    CLOSING = "closing", _("clôture")


class Session(TimeStampedModel):
    """Session d'un jour de l'édition : type, titres, salle (nulle pour un événement hors
    salle), début et fin en UTC (saisis à l'heure de l'édition, D13, I12)."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="program_sessions",
    )
    kind = models.CharField(_("type"), max_length=16, choices=SessionKind.choices)
    title_fr = models.CharField(_("titre (FR)"), max_length=255)
    title_en = models.CharField(_("titre (EN)"), max_length=255, blank=True, default="")
    description_fr = models.TextField(_("description (FR)"), blank=True, default="")
    description_en = models.TextField(_("description (EN)"), blank=True, default="")
    track = models.ForeignKey(
        "conferences.Track",
        verbose_name=_("thématique"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    room = models.ForeignKey(
        Room,
        verbose_name=_("salle"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="sessions",
    )
    starts_at = models.DateTimeField(_("début"))
    ends_at = models.DateTimeField(_("fin"))
    instructions = models.TextField(_("consignes"), blank=True, default="")

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "kind",
        "title_fr",
        "title_en",
        "track",
        "room",
        "starts_at",
        "ends_at",
        "instructions",
    )

    class Meta:
        verbose_name = _("session")
        verbose_name_plural = _("sessions")
        ordering = ("edition", "starts_at", "room", "id")
        constraints = (
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")), name="prog_session_order"
            ),
        )
        indexes = (
            models.Index(fields=["room", "starts_at"], name="prog_session_room"),
            models.Index(fields=["edition", "starts_at"], name="prog_session_start"),
        )

    def __str__(self) -> str:
        return self.title_fr


class Slot(TimeStampedModel):
    """Créneau d'une session (I3) : une communication **ou** un élément libre (titre, avec
    ou sans intervenant invité). Une communication n'occupe qu'un créneau (unicité). Début et
    fin calculés par le service de planification."""

    session = models.ForeignKey(
        Session, verbose_name=_("session"), on_delete=models.RESTRICT, related_name="slots"
    )
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    duration_min = models.PositiveSmallIntegerField(
        _("durée (minutes)"), validators=[MinValueValidator(1), MaxValueValidator(600)]
    )
    starts_at = models.DateTimeField(_("début"))
    ends_at = models.DateTimeField(_("fin"))
    submission = models.OneToOneField(
        "submissions.Submission",
        verbose_name=_("communication"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="program_slot",
    )
    title_fr = models.CharField(_("titre libre (FR)"), max_length=300, blank=True, default="")
    title_en = models.CharField(_("titre libre (EN)"), max_length=300, blank=True, default="")
    speaker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("intervenant invité"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="program_slots",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "session",
        "position",
        "duration_min",
        "starts_at",
        "ends_at",
        "submission",
        "title_fr",
        "title_en",
        "speaker",
    )

    class Meta:
        verbose_name = _("créneau")
        verbose_name_plural = _("créneaux")
        ordering = ("session", "position", "id")
        constraints = (
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="prog_slot_order"),
            # Une communication, ou un titre libre (I3).
            models.CheckConstraint(
                condition=Q(submission__isnull=False) | ~Q(title_fr=""),
                name="prog_slot_content",
            ),
        )
        indexes = (models.Index(fields=["starts_at"], name="prog_slot_start"),)

    def __str__(self) -> str:
        return f"{self.session_id}:{self.position}"


class SessionRoleKind(models.TextChoices):
    CHAIR = "chair", _("président de séance")
    DISCUSSANT = "discussant", _("discutant")
    MODERATOR = "moderator", _("modérateur")
    PANELIST = "panelist", _("panéliste")


class SessionRole(models.Model):
    """Rôle d'une personne dans une session (I10) : toujours un compte (« Mon passage »)."""

    session = models.ForeignKey(
        Session, verbose_name=_("session"), on_delete=models.RESTRICT, related_name="roles"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("personne"),
        on_delete=models.RESTRICT,
        related_name="session_roles",
    )
    role = models.CharField(_("rôle"), max_length=12, choices=SessionRoleKind.choices)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("session", "user", "role")

    class Meta:
        verbose_name = _("rôle de séance")
        verbose_name_plural = _("rôles de séance")
        ordering = ("session", "role", "id")
        constraints = (
            models.UniqueConstraint(fields=["session", "user", "role"], name="prog_role_once"),
        )

    def __str__(self) -> str:
        return f"{self.session_id}:{self.user_id}:{self.role}"


# --- État et publications (I6, I14) --------------------------------------------------------


class ProgramState(models.Model):
    """État du programme d'une édition : **révision** du brouillon, incrémentée à chaque
    écriture et contrôlée par ``If-Match`` (I14), et révision publiée (modifications non
    publiées = écart des deux). La ligne est verrouillée par chaque écriture de planification,
    ce qui met en série les contrôles de conflits sans verrouiller l'édition elle-même."""

    edition = models.OneToOneField(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="program_state",
    )
    revision = models.PositiveIntegerField(_("révision du brouillon"), default=0)
    published_revision = models.PositiveIntegerField(_("révision publiée"), default=0)
    published_version = models.PositiveIntegerField(_("dernière version publiée"), default=0)

    class Meta:
        verbose_name = _("état du programme")
        verbose_name_plural = _("états du programme")

    def __str__(self) -> str:
        return f"{self.edition_id}:{self.revision}"


class ProgramPublication(AppendOnlyModel):
    """Publication du programme (I6) : instantané numéroté, en ajout seul. Seule source du
    programme public et de « Mon passage ». ``summary`` : différences avec la version
    précédente (I13, I16)."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="program_publications",
    )
    version = models.PositiveIntegerField(_("version"))
    revision = models.PositiveIntegerField(_("révision publiée"))
    published_at = models.DateTimeField(_("publiée le"))
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("publiée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    snapshot = models.JSONField(_("instantané"))
    summary = models.JSONField(_("différences"), default=dict)

    @classmethod
    def redact(cls, edition_ids: list[int], scrub: Any) -> int:
        """Réécrit les instantanés d'une personne anonymisée (RG-18) : noms et affiliations
        retirés des communications et des rôles de séance."""
        count = 0
        for row in cls.objects.filter(edition_id__in=edition_ids):
            cleaned = scrub(row.snapshot)
            if cleaned != row.snapshot:
                cls.objects.filter(pk=row.pk)._unchecked_update(snapshot=cleaned)
                count += 1
        return count

    class Meta:
        verbose_name = _("publication du programme")
        verbose_name_plural = _("publications du programme")
        ordering = ("edition", "-version")
        constraints = (
            models.UniqueConstraint(fields=["edition", "version"], name="prog_publication_once"),
        )

    def __str__(self) -> str:
        return f"{self.edition_id} v{self.version}"


# --- Confirmation de présentation (I5) -----------------------------------------------------


class PresentationConfirmation(TimeStampedModel):
    """Confirmation de présentation par le soumissionnaire (I5) : présentateurs désignés
    parmi les auteurs (positions dans ``submission.authors``). Fait passer la communication
    ``CAMERA_READY_RECEIVED → CONFIRMED`` (par ``transition()``, règle n° 4)."""

    submission = models.OneToOneField(
        "submissions.Submission",
        verbose_name=_("communication"),
        on_delete=models.RESTRICT,
        related_name="presentation_confirmation",
    )
    presenters = models.JSONField(_("présentateurs (positions des auteurs)"), default=list)
    confirmed_at = models.DateTimeField(_("confirmée le"))
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("confirmée par"),
        on_delete=models.RESTRICT,
        related_name="+",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("presenters", "confirmed_at")

    class Meta:
        verbose_name = _("confirmation de présentation")
        verbose_name_plural = _("confirmations de présentation")

    def __str__(self) -> str:
        return str(self.submission_id)
