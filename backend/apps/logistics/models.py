"""Organisation et logistique (plan L8 §3 ; étude M10, M11, §8.2).

L8.2 : tâches du CO (N3) et budget (N4). L8.4 : fiches de venue des intervenants invités,
régimes alimentaires, repas et planning des bénévoles. Les modèles arrivent avec leurs
services, par migrations additives (comme en L7).
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel
from apps.registrations.models import money_field


class TaskStatus(models.TextChoices):
    """Colonnes du kanban (N3)."""

    TODO = "todo", _("à faire")
    DOING = "doing", _("en cours")
    DONE = "done", _("terminée")


class TaskPriority(models.TextChoices):
    LOW = "low", _("basse")
    NORMAL = "normal", _("normale")
    HIGH = "high", _("haute")


class Task(TimeStampedModel):
    """Tâche du comité d'organisation (N3, étude §8.2 ``task``).

    Écrite par ``apps.logistics.services.tasks`` seul : révision incrémentée à chaque
    écriture (``If-Match``, 412 si elle a changé), journal ``task.*``. Jamais supprimée :
    archivée.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="tasks",
    )
    title = models.CharField(_("titre"), max_length=200)
    description = models.TextField(_("description"), blank=True, default="")
    status = models.CharField(
        _("statut"), max_length=8, choices=TaskStatus.choices, default=TaskStatus.TODO
    )
    priority = models.CharField(
        _("priorité"), max_length=8, choices=TaskPriority.choices, default=TaskPriority.NORMAL
    )
    label = models.CharField(_("étiquette"), max_length=50, blank=True, default="")
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("responsable"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="assigned_tasks",
    )
    due_date = models.DateField(_("échéance"), null=True, blank=True)
    position = models.PositiveIntegerField(_("position dans la colonne"), default=0)
    revision = models.PositiveIntegerField(_("révision"), default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créée par"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )
    done_at = models.DateTimeField(_("terminée le"), null=True, blank=True)
    archived_at = models.DateTimeField(_("archivée le"), null=True, blank=True)
    # Dernier récapitulatif envoyé au responsable (``remind_tasks``, idempotence du jour).
    reminded_on = models.DateField(_("rappelée le"), null=True, blank=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "title",
        "description",
        "status",
        "priority",
        "label",
        "assignee",
        "due_date",
    )

    class Meta:
        verbose_name = _("tâche")
        verbose_name_plural = _("tâches")
        ordering = ("edition", "status", "position", "id")
        indexes = (
            models.Index(fields=("edition", "status", "position"), name="log_task_column"),
            models.Index(fields=("assignee", "due_date"), name="log_task_assignee"),
        )

    def __str__(self) -> str:
        return self.title


class TaskComment(TimeStampedModel):
    """Commentaire d'une tâche (N3) ; jamais modifié ni supprimé (auteur anonymisé avec son
    compte)."""

    task = models.ForeignKey(
        Task, verbose_name=_("tâche"), on_delete=models.RESTRICT, related_name="comments"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("auteur"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    body = models.TextField(_("texte"))

    class Meta:
        verbose_name = _("commentaire de tâche")
        verbose_name_plural = _("commentaires de tâche")
        ordering = ("task", "created_at", "id")


class TaskAttachment(TimeStampedModel):
    """Pièce jointe d'une tâche (N3) : PDF, PNG ou JPEG, type vérifié par contenu, fichier
    privé (règle n° 8). Les documents partagés du CO (M11) passent par là."""

    task = models.ForeignKey(
        Task, verbose_name=_("tâche"), on_delete=models.RESTRICT, related_name="attachments"
    )
    storage_name = models.CharField(_("nom de stockage"), max_length=64, unique=True)
    name = models.CharField(_("nom du fichier"), max_length=255)
    kind = models.CharField(_("type"), max_length=8)
    size = models.PositiveIntegerField(_("taille (octets)"))
    sha256 = models.CharField(_("empreinte"), max_length=64)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("déposée par"),
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("pièce jointe de tâche")
        verbose_name_plural = _("pièces jointes de tâche")
        ordering = ("task", "created_at", "id")


class BudgetKind(models.TextChoices):
    EXPENSE = "expense", _("dépense")
    INCOME = "income", _("recette")


class BudgetCategory(models.TextChoices):
    """Postes du budget (N4), catalogue fermé : dépenses puis recettes."""

    VENUE = "venue", _("lieu")
    CATERING = "catering", _("restauration")
    TRAVEL = "travel", _("voyages")
    ACCOMMODATION = "accommodation", _("hébergement")
    COMMUNICATION = "communication", _("communication")
    PRINTING = "printing", _("impression")
    EQUIPMENT = "equipment", _("matériel")
    STAFF = "staff", _("personnel")
    OTHER_EXPENSE = "other_expense", _("divers (dépense)")
    REGISTRATIONS = "registrations", _("inscriptions")
    SPONSORSHIP = "sponsorship", _("partenariats")
    GRANTS = "grants", _("subventions")
    OTHER_INCOME = "other_income", _("divers (recette)")


EXPENSE_CATEGORIES = frozenset(
    {
        BudgetCategory.VENUE,
        BudgetCategory.CATERING,
        BudgetCategory.TRAVEL,
        BudgetCategory.ACCOMMODATION,
        BudgetCategory.COMMUNICATION,
        BudgetCategory.PRINTING,
        BudgetCategory.EQUIPMENT,
        BudgetCategory.STAFF,
        BudgetCategory.OTHER_EXPENSE,
    }
)


class BudgetSource(models.TextChoices):
    """Origine du réalisé (N4) : saisi, ou calculé (encaissé net des inscriptions de L6,
    contributions reçues des partenaires de L8.3)."""

    MANUAL = "manual", _("saisi")
    REGISTRATIONS = "registrations", _("calculé : inscriptions")
    SPONSORS = "sponsors", _("calculé : partenaires")


class BudgetLine(TimeStampedModel):
    """Ligne du budget prévisionnel et réalisé (N4, étude §8.2 ``budget_line``), en
    ``Decimal`` exact dans la devise de l'édition.

    Une ligne calculée (``source`` ≠ ``manual``) n'a pas de réalisé saisi (``actual`` nul) :
    le service le calcule à la lecture. Une seule ligne calculée par source et par édition.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="budget_lines",
    )
    kind = models.CharField(_("nature"), max_length=8, choices=BudgetKind.choices)
    category = models.CharField(_("poste"), max_length=16, choices=BudgetCategory.choices)
    label = models.CharField(_("libellé"), max_length=200)
    planned = money_field(_("prévu"), default=0)
    actual = money_field(_("réalisé"), null=True, blank=True)
    source = models.CharField(
        _("origine du réalisé"),
        max_length=16,
        choices=BudgetSource.choices,
        default=BudgetSource.MANUAL,
    )
    # Clé d'unicité des lignes calculées ; nulle pour une ligne saisie (pas d'index unique
    # partiel sur MariaDB).
    computed_key = models.CharField(max_length=32, null=True, blank=True, unique=True)
    note = models.TextField(_("note"), blank=True, default="")
    position = models.PositiveIntegerField(_("position"), default=0)
    proof_storage_name = models.CharField(
        _("justificatif (nom de stockage)"), max_length=64, blank=True, default=""
    )
    proof_name = models.CharField(_("justificatif"), max_length=255, blank=True, default="")
    proof_kind = models.CharField(_("type du justificatif"), max_length=8, blank=True, default="")
    proof_size = models.PositiveIntegerField(_("taille du justificatif"), null=True, blank=True)

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "kind",
        "category",
        "label",
        "planned",
        "actual",
        "note",
    )

    class Meta:
        verbose_name = _("ligne de budget")
        verbose_name_plural = _("lignes de budget")
        ordering = ("edition", "kind", "position", "id")
        constraints = (
            models.CheckConstraint(condition=Q(planned__gte=0), name="log_budget_planned_pos"),
            models.CheckConstraint(
                condition=Q(actual__isnull=True) | Q(actual__gte=0),
                name="log_budget_actual_pos",
            ),
            models.CheckConstraint(
                condition=Q(source="manual") | Q(actual__isnull=True),
                name="log_budget_computed_actual",
            ),
        )

    def __str__(self) -> str:
        return self.label
