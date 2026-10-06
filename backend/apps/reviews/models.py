"""Évaluation et décision (plan L4 §3 ; étude §5.1, §8.2 « Évaluation »).

Les statuts des soumissions changent par ``apps.submissions.workflow.transition`` seul
(règle n° 4) ; ce module porte les grilles, affectations, évaluations, conflits, discussions,
décisions et versions finales. Scores et poids en ``Decimal`` (convention de ``CLAUDE.md``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyModel, TimeStampedModel

# --- Grilles (RG-05, H3) ----------------------------------------------------------------------


class EvaluationGrid(TimeStampedModel):
    """Grille d'une édition, pour un type de communication ou pour tous (``submission_type``
    nul). Verrouillée dès la première évaluation enregistrée (``locked_at``) : on la duplique
    en nouvelle version. ``scope_key`` garantit une version unique par (édition, type ou
    « tous ») sans unicité conditionnelle (plan L1 §3.1)."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="grids",
    )
    submission_type = models.ForeignKey(
        "conferences.SubmissionType",
        verbose_name=_("type de communication"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    version = models.PositiveSmallIntegerField(_("version"), default=1)
    name = models.CharField(_("nom"), max_length=150)
    scale_min = models.PositiveSmallIntegerField(_("note minimale"), default=0)
    scale_max = models.PositiveSmallIntegerField(
        _("note maximale"), default=5, validators=[MaxValueValidator(100)]
    )
    locked_at = models.DateTimeField(_("verrouillée le"), null=True, blank=True)
    scope_key = models.CharField(_("clé d'unicité"), max_length=64, unique=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "submission_type",
        "version",
        "name",
        "scale_min",
        "scale_max",
        "locked_at",
    )

    class Meta:
        verbose_name = _("grille d'évaluation")
        verbose_name_plural = _("grilles d'évaluation")
        ordering = ("edition", "submission_type", "-version", "id")
        constraints = (
            models.CheckConstraint(
                condition=Q(scale_min__lt=F("scale_max")), name="rev_grid_scale_order"
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class Criterion(models.Model):
    """Critère pondéré. Supprimé avec sa grille (``CASCADE`` : il n'existe pas sans elle, et
    une grille ne se supprime que tant qu'elle n'est pas verrouillée)."""

    grid = models.ForeignKey(
        EvaluationGrid,
        verbose_name=_("grille"),
        on_delete=models.CASCADE,
        related_name="criteria",
    )
    code = models.SlugField(_("code"), max_length=32)
    label_fr = models.CharField(_("libellé (FR)"), max_length=255)
    label_en = models.CharField(_("libellé (EN)"), max_length=255, blank=True, default="")
    help_fr = models.TextField(_("aide à la notation (FR)"), blank=True, default="")
    help_en = models.TextField(_("aide à la notation (EN)"), blank=True, default="")
    weight = models.DecimalField(
        _("poids (%)"),
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))],
    )
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    is_required = models.BooleanField(_("obligatoire"), default=True)

    class Meta:
        verbose_name = _("critère")
        verbose_name_plural = _("critères")
        ordering = ("grid", "position", "id")
        constraints = (
            models.UniqueConstraint(fields=["grid", "code"], name="rev_criterion_code"),
            models.CheckConstraint(condition=Q(weight__gt=0), name="rev_criterion_weight"),
        )

    def __str__(self) -> str:
        return self.code


# --- Relecteurs, affectations, conflits (H6 à H8) -------------------------------------------


class ReviewerTrack(models.Model):
    """Thématique de compétence déclarée par un relecteur pour une édition (H7)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("relecteur"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    edition = models.ForeignKey(
        "conferences.Edition", verbose_name=_("édition"), on_delete=models.RESTRICT
    )
    track = models.ForeignKey(
        "conferences.Track", verbose_name=_("thématique"), on_delete=models.RESTRICT
    )

    class Meta:
        verbose_name = _("expertise")
        verbose_name_plural = _("expertises")
        constraints = (
            models.UniqueConstraint(fields=["user", "edition", "track"], name="rev_reviewer_track"),
        )

    def __str__(self) -> str:
        return f"{self.user_id}:{self.track_id}"


class AssignmentStatus(models.TextChoices):
    ACTIVE = "active", _("active")
    DECLINED = "declined", _("déclinée")
    CANCELLED = "cancelled", _("annulée")


class ReviewAssignment(TimeStampedModel):
    """Affectation d'un relecteur à une soumission (H6). Une seule affectation **active** par
    (soumission, relecteur) : ``active_key`` n'est renseignée que tant qu'elle est active.
    ``pseudonym_rank`` : numéro du pseudonyme (« Relecteur N », H11), tiré au hasard à
    l'affectation pour ne pas révéler l'ordre d'affectation."""

    submission = models.ForeignKey(
        "submissions.Submission",
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="assignments",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("relecteur"),
        on_delete=models.RESTRICT,
        related_name="review_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("affectée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    assigned_at = models.DateTimeField(_("affectée le"))
    due_at = models.DateTimeField(_("échéance"), null=True, blank=True)
    status = models.CharField(
        _("statut"),
        max_length=10,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
    )
    reason = models.TextField(_("motif (refus ou annulation)"), blank=True, default="")
    conflict_override_reason = models.TextField(
        _("motif de la levée de conflit"), blank=True, default=""
    )
    # Relances envoyées (H15) : codes « j7 », « j1 », « late », une fois chacun.
    reminders = models.JSONField(_("relances envoyées"), default=list, blank=True)
    pseudonym_rank = models.PositiveSmallIntegerField(_("rang du pseudonyme"), default=0)
    active_key = models.CharField(
        _("clé d'unicité active"), max_length=64, null=True, blank=True, unique=True
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("status", "due_at", "reason")

    class Meta:
        verbose_name = _("affectation")
        verbose_name_plural = _("affectations")
        ordering = ("submission", "pseudonym_rank", "id")
        indexes = (models.Index(fields=["reviewer", "status"], name="rev_assignment_reviewer"),)

    def __str__(self) -> str:
        return f"{self.submission_id}:{self.reviewer_id}"


class ConflictSource(models.TextChoices):
    REVIEWER = "reviewer", _("déclaré par le relecteur")
    SYSTEM = "system", _("détecté par le système")
    CHAIR = "chair", _("déclaré par le président")


class ConflictKind(models.TextChoices):
    AUTHOR = "author", _("auteur de la soumission")
    INSTITUTION = "institution", _("même institution")
    DECLARED = "declared", _("déclaré")


class ConflictOfInterest(TimeStampedModel):
    """Conflit d'intérêts (H8). ``author`` : bloquant sans exception. ``institution`` et
    ``declared`` : bloquants, levables par le président avec un motif journalisé."""

    submission = models.ForeignKey(
        "submissions.Submission",
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="conflicts",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("relecteur"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    source = models.CharField(_("origine"), max_length=10, choices=ConflictSource.choices)
    kind = models.CharField(_("nature"), max_length=12, choices=ConflictKind.choices)
    reason = models.TextField(_("motif"), blank=True, default="")
    declared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("déclaré par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    overridden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("levé par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    overridden_at = models.DateTimeField(_("levé le"), null=True, blank=True)
    overridden_reason = models.TextField(_("motif de la levée"), blank=True, default="")

    class Meta:
        verbose_name = _("conflit d'intérêts")
        verbose_name_plural = _("conflits d'intérêts")
        ordering = ("submission", "reviewer", "id")
        constraints = (
            models.UniqueConstraint(
                fields=["submission", "reviewer", "kind"], name="rev_conflict_once"
            ),
        )

    def __str__(self) -> str:
        return f"{self.submission_id}:{self.reviewer_id}:{self.kind}"


# --- Évaluations (H4, H5, RG-06) --------------------------------------------------------------


class ReviewStatus(models.TextChoices):
    DRAFT = "draft", _("brouillon")
    SUBMITTED = "submitted", _("envoyée")


class Recommendation(models.TextChoices):
    ACCEPT = "accept", _("accepter")
    ACCEPT_MINOR = "accept_minor", _("accepter avec corrections")
    REJECT = "reject", _("rejeter")
    DISCUSS = "discuss", _("discuter")


class Review(TimeStampedModel):
    """Évaluation d'une affectation. ``weighted_score`` (sur 100) est calculé par le serveur
    à chaque enregistrement, jamais lu du client (H4) ; ``version`` compte les envois
    (RG-06 : chaque envoi est historisé dans ``ReviewVersion``)."""

    assignment = models.OneToOneField(
        ReviewAssignment,
        verbose_name=_("affectation"),
        on_delete=models.RESTRICT,
        related_name="review",
    )
    grid = models.ForeignKey(
        EvaluationGrid, verbose_name=_("grille"), on_delete=models.RESTRICT, related_name="+"
    )
    status = models.CharField(
        _("statut"), max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.DRAFT
    )
    recommendation = models.CharField(
        _("recommandation"),
        max_length=16,
        choices=Recommendation.choices,
        blank=True,
        default="",
    )
    confidence = models.PositiveSmallIntegerField(
        _("confiance"),
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment_to_authors = models.TextField(_("commentaire aux auteurs"), blank=True, default="")
    comment_to_committee = models.TextField(_("commentaire au comité"), blank=True, default="")
    ethics_flag = models.BooleanField(_("signalement d'éthique"), default=False)
    plagiarism_flag = models.BooleanField(_("plagiat présumé"), default=False)
    suggested_type = models.ForeignKey(
        "conferences.SubmissionType",
        verbose_name=_("format suggéré"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    weighted_score = models.DecimalField(
        _("note pondérée (sur 100)"), max_digits=5, decimal_places=2, null=True, blank=True
    )
    submitted_at = models.DateTimeField(_("envoyée le"), null=True, blank=True)
    version = models.PositiveIntegerField(_("version"), default=0)

    class Meta:
        verbose_name = _("évaluation")
        verbose_name_plural = _("évaluations")
        constraints = (
            models.CheckConstraint(
                condition=Q(confidence__isnull=True) | Q(confidence__gte=1, confidence__lte=5),
                name="rev_review_confidence",
            ),
        )

    def __str__(self) -> str:
        return f"review-{self.pk}"


class ReviewScore(models.Model):
    """Note d'un critère (échelle de la grille). Supprimée avec l'évaluation (``CASCADE`` :
    partie de l'évaluation, qui ne se supprime pas elle-même)."""

    review = models.ForeignKey(
        Review, verbose_name=_("évaluation"), on_delete=models.CASCADE, related_name="scores"
    )
    criterion = models.ForeignKey(
        Criterion, verbose_name=_("critère"), on_delete=models.RESTRICT, related_name="+"
    )
    value = models.DecimalField(_("note"), max_digits=4, decimal_places=1)

    class Meta:
        verbose_name = _("note de critère")
        verbose_name_plural = _("notes de critère")
        constraints = (
            models.UniqueConstraint(fields=["review", "criterion"], name="rev_score_once"),
        )

    def __str__(self) -> str:
        return f"{self.review_id}:{self.criterion_id}"


class ReviewVersion(AppendOnlyModel):
    """Envoi d'une évaluation (RG-06) : cliché complet, en ajout seul."""

    review = models.ForeignKey(
        Review, verbose_name=_("évaluation"), on_delete=models.RESTRICT, related_name="versions"
    )
    version = models.PositiveIntegerField(_("version"))
    at = models.DateTimeField(_("date"))
    snapshot = models.JSONField(_("cliché"))

    @classmethod
    def redact(cls, review_ids: list[int], scrub: Any) -> int:
        """Réécrit les commentaires des clichés (anonymisation du relecteur)."""
        count = 0
        for row in cls.objects.filter(review_id__in=review_ids):
            cleaned = scrub(row.snapshot)
            if cleaned != row.snapshot:
                cls.objects.filter(pk=row.pk)._unchecked_update(snapshot=cleaned)
                count += 1
        return count

    class Meta:
        verbose_name = _("version d'évaluation")
        verbose_name_plural = _("versions d'évaluation")
        ordering = ("review", "version")
        constraints = (
            models.UniqueConstraint(fields=["review", "version"], name="rev_version_once"),
        )


# --- Discussion (RG-08, H12) -------------------------------------------------------------------


class Discussion(models.Model):
    """Discussion d'une soumission entre ses relecteurs et le président (RG-08)."""

    submission = models.OneToOneField(
        "submissions.Submission",
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="discussion",
    )
    opened_at = models.DateTimeField(_("ouverte le"))
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("ouverte par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("discussion")
        verbose_name_plural = _("discussions")

    def __str__(self) -> str:
        return f"discussion-{self.submission_id}"


class DiscussionMessage(models.Model):
    """Message de discussion ; l'auteur est affiché sous pseudonyme aux relecteurs (H11)."""

    discussion = models.ForeignKey(
        Discussion,
        verbose_name=_("discussion"),
        on_delete=models.RESTRICT,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("auteur du message"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    body = models.TextField(_("message"))
    at = models.DateTimeField(_("date"))

    class Meta:
        verbose_name = _("message de discussion")
        verbose_name_plural = _("messages de discussion")
        ordering = ("discussion", "at", "id")

    def __str__(self) -> str:
        return f"message-{self.pk}"


# --- Décisions et version finale (H16, H18, RG-09) --------------------------------------------


class DecisionOutcome(models.TextChoices):
    ACCEPTED = "accepted", _("acceptée")
    ACCEPTED_MINOR = "accepted_minor", _("acceptée sous réserve de corrections")
    WAITLIST = "waitlist", _("liste d'attente")
    REJECTED = "rejected", _("rejetée")


class Decision(TimeStampedModel):
    """Décision **provisoire** tant que ``published_at`` est nul (H16) : les statuts des
    soumissions et les e-mails n'interviennent qu'à la publication (RG-09)."""

    submission = models.OneToOneField(
        "submissions.Submission",
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="decision",
    )
    outcome = models.CharField(_("issue"), max_length=16, choices=DecisionOutcome.choices)
    assigned_type = models.ForeignKey(
        "conferences.SubmissionType",
        verbose_name=_("format attribué"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    comment_to_authors = models.TextField(_("commentaire aux auteurs"), blank=True, default="")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("décidée par"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    decided_at = models.DateTimeField(_("décidée le"))
    published_at = models.DateTimeField(_("publiée le"), null=True, blank=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = ("outcome", "assigned_type", "published_at")

    class Meta:
        verbose_name = _("décision")
        verbose_name_plural = _("décisions")

    def __str__(self) -> str:
        return f"decision-{self.submission_id}"


class FinalVersion(TimeStampedModel):
    """Version finale d'une soumission acceptée (H18) : PDF nominatif (fichier de nature
    ``camera_ready``) et lettre de réponse aux relecteurs."""

    submission = models.OneToOneField(
        "submissions.Submission",
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="final_version",
    )
    file = models.ForeignKey(
        "submissions.SubmissionFile",
        verbose_name=_("fichier"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    response_letter = models.TextField(_("lettre de réponse"), blank=True, default="")
    submitted_at = models.DateTimeField(_("déposée le"))

    class Meta:
        verbose_name = _("version finale")
        verbose_name_plural = _("versions finales")

    def __str__(self) -> str:
        return f"final-{self.submission_id}"
