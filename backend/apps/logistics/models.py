"""Organisation et logistique (plan L8 §3 ; étude M10, M11, §8.2).

L8.2 : tâches du CO (N3) et budget (N4). L8.4 : fiches de venue des intervenants invités,
régimes alimentaires, repas et planning des bénévoles. Les modèles arrivent avec leurs
services, par migrations additives (comme en L7).
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import F, Q
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


# --- L8.4 : intervenants invités, régimes, repas, bénévoles ------------------------------------


class TravelMeans(models.TextChoices):
    PLANE = "plane", _("avion")
    TRAIN = "train", _("train")
    ROAD = "road", _("route")
    OTHER = "other", _("autre")


class VisitStatus(models.TextChoices):
    """Prise en charge de la venue d'un intervenant invité (N6)."""

    TO_ARRANGE = "to_arrange", _("à organiser")
    BOOKED = "booked", _("réservée")
    CONFIRMED = "confirmed", _("confirmée")


class SpeakerVisit(TimeStampedModel):
    """Fiche de venue d'un intervenant invité (N6) : besoins, voyage, hébergement.

    L'intervenant écrit sa part (besoins, arrivée, départ, demandes) depuis le portail ; le
    CO « logistique » écrit le reste. La **note interne** n'est jamais servie à l'intervenant.
    Effacée 30 jours après la fin de l'édition (N15).
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="speaker_visits",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("intervenant"),
        on_delete=models.RESTRICT,
        related_name="speaker_visits",
    )
    technical_needs = models.JSONField(_("besoins techniques"), default=list, blank=True)
    technical_note = models.TextField(_("précisions techniques"), blank=True, default="")
    arrival_at = models.DateTimeField(_("arrivée"), null=True, blank=True)
    arrival_means = models.CharField(
        _("moyen d'arrivée"), max_length=8, choices=TravelMeans.choices, blank=True, default=""
    )
    arrival_reference = models.CharField(
        _("vol ou train (arrivée)"), max_length=60, blank=True, default=""
    )
    departure_at = models.DateTimeField(_("départ"), null=True, blank=True)
    departure_means = models.CharField(
        _("moyen de départ"), max_length=8, choices=TravelMeans.choices, blank=True, default=""
    )
    departure_reference = models.CharField(
        _("vol ou train (départ)"), max_length=60, blank=True, default=""
    )
    accommodation_needed = models.BooleanField(_("hébergement demandé"), default=False)
    transfer_needed = models.BooleanField(_("transfert demandé"), default=False)
    speaker_note = models.TextField(_("demandes de l'intervenant"), blank=True, default="")
    hotel = models.CharField(_("hôtel"), max_length=150, blank=True, default="")
    check_in = models.DateField(_("arrivée à l'hôtel"), null=True, blank=True)
    check_out = models.DateField(_("départ de l'hôtel"), null=True, blank=True)
    status = models.CharField(
        _("prise en charge"),
        max_length=12,
        choices=VisitStatus.choices,
        default=VisitStatus.TO_ARRANGE,
    )
    internal_note = models.TextField(_("note interne"), blank=True, default="")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("mise à jour par"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )

    SPEAKER_FIELDS: ClassVar[tuple[str, ...]] = (
        "technical_needs",
        "technical_note",
        "arrival_at",
        "arrival_means",
        "arrival_reference",
        "departure_at",
        "departure_means",
        "departure_reference",
        "accommodation_needed",
        "transfer_needed",
        "speaker_note",
    )
    STAFF_FIELDS: ClassVar[tuple[str, ...]] = (
        "hotel",
        "check_in",
        "check_out",
        "status",
        "internal_note",
    )

    class Meta:
        verbose_name = _("fiche de venue")
        verbose_name_plural = _("fiches de venue")
        ordering = ("edition", "id")
        constraints = (
            models.UniqueConstraint(fields=("edition", "user"), name="log_visit_unique"),
        )


class Diet(models.TextChoices):
    """Régimes alimentaires proposés (N7, catalogue fermé)."""

    VEGETARIAN = "vegetarian", _("végétarien")
    VEGAN = "vegan", _("végétalien")
    NO_PORK = "no_pork", _("sans porc")
    GLUTEN_FREE = "gluten_free", _("sans gluten")
    LACTOSE_FREE = "lactose_free", _("sans lactose")
    OTHER = "other", _("autre")


class DietaryDeclaration(TimeStampedModel):
    """Régime alimentaire déclaré pour une édition (N7, RG-23) : facultatif, avec
    consentement explicite (donnée pouvant révéler la santé ou des convictions), retirable,
    effacé 30 jours après la fin de l'édition."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="dietary_declarations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("personne"),
        on_delete=models.RESTRICT,
        related_name="dietary_declarations",
    )
    diets = models.JSONField(_("régimes"), default=list, blank=True)
    allergies = models.CharField(_("allergies"), max_length=200, blank=True, default="")
    consented_at = models.DateTimeField(_("consentement donné le"))

    class Meta:
        verbose_name = _("régime alimentaire")
        verbose_name_plural = _("régimes alimentaires")
        ordering = ("edition", "id")
        constraints = (models.UniqueConstraint(fields=("edition", "user"), name="log_diet_unique"),)


class MealKind(models.TextChoices):
    COFFEE_BREAK = "coffee_break", _("pause café")
    LUNCH = "lunch", _("déjeuner")
    DINNER = "dinner", _("dîner")
    COCKTAIL = "cocktail", _("cocktail")


class Meal(TimeStampedModel):
    """Repas de l'édition (N8) et son public ; l'effectif est calculé, jamais saisi."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="meals",
    )
    day = models.DateField(_("jour"))
    kind = models.CharField(_("type"), max_length=14, choices=MealKind.choices)
    label_fr = models.CharField(_("libellé (FR)"), max_length=150, blank=True, default="")
    label_en = models.CharField(_("libellé (EN)"), max_length=150, blank=True, default="")
    # Inscrits confirmés, tous ou titulaires d'une option de L6 (« diner », par exemple).
    include_registered = models.BooleanField(_("inscrits confirmés"), default=True)
    option_code = models.CharField(_("option requise"), max_length=32, blank=True, default="")
    include_speakers = models.BooleanField(_("intervenants invités"), default=True)
    include_committees = models.BooleanField(_("membres des comités"), default=False)
    include_volunteers = models.BooleanField(_("bénévoles"), default=False)
    margin_percent = models.PositiveSmallIntegerField(_("marge (%)"), default=5)
    position = models.PositiveIntegerField(_("ordre"), default=0)

    class Meta:
        verbose_name = _("repas")
        verbose_name_plural = _("repas")
        ordering = ("edition", "day", "position", "id")
        constraints = (
            models.CheckConstraint(condition=Q(margin_percent__lte=50), name="log_meal_margin"),
        )


class VolunteerShift(TimeStampedModel):
    """Poste de bénévolat (N9) : intitulé, lieu, horaire, nombre de bénévoles nécessaires."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="volunteer_shifts",
    )
    title_fr = models.CharField(_("intitulé (FR)"), max_length=150)
    title_en = models.CharField(_("intitulé (EN)"), max_length=150, blank=True, default="")
    place = models.CharField(_("lieu"), max_length=150, blank=True, default="")
    starts_at = models.DateTimeField(_("début"))
    ends_at = models.DateTimeField(_("fin"))
    needed = models.PositiveSmallIntegerField(_("bénévoles nécessaires"), default=1)
    instructions = models.TextField(_("consignes"), blank=True, default="")

    class Meta:
        verbose_name = _("poste de bénévolat")
        verbose_name_plural = _("postes de bénévolat")
        ordering = ("edition", "starts_at", "id")
        constraints = (
            models.CheckConstraint(condition=Q(ends_at__gt=F("starts_at")), name="log_shift_order"),
            models.CheckConstraint(condition=Q(needed__gte=1), name="log_shift_needed"),
        )


class ShiftAssignment(TimeStampedModel):
    """Affectation d'un bénévole à un poste (N9) ; deux postes qui se chevauchent pour la même
    personne sont refusés par le service."""

    shift = models.ForeignKey(
        VolunteerShift,
        verbose_name=_("poste"),
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    volunteer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("bénévole"),
        on_delete=models.RESTRICT,
        related_name="shift_assignments",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("affecté par"),
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = _("affectation de bénévole")
        verbose_name_plural = _("affectations de bénévoles")
        ordering = ("shift", "id")
        constraints = (
            models.UniqueConstraint(fields=("shift", "volunteer"), name="log_shift_assignment"),
        )
