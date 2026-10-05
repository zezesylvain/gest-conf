"""Soumissions (lot L3, plan ``docs/L3-soumission-plan.md`` §3 ; étude §8.2).

Le champ ``status`` n'est écrit que par ``apps.submissions.workflow.transition`` (règle
n° 4, vérifié par un méta-test). Les fichiers sont privés (règle n° 8, sans adaptation) :
stockés hors racine web sous un nom aléatoire, servis par un endpoint authentifié.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import AppendOnlyModel, TimeStampedModel


class SubmissionStatus(models.TextChoices):
    """Statuts de l'étude (M6, §5.1). L3 n'active que brouillon, soumise, recevabilité et
    retrait ; les autres sont déclarés pour que le workflow soit complet dès L3."""

    DRAFT = "draft", _("brouillon")
    SUBMITTED = "submitted", _("soumise")
    SCREENING = "screening", _("vérification de recevabilité")
    UNDER_REVIEW = "under_review", _("en cours d'évaluation")
    REVIEWED = "reviewed", _("évaluée")
    ACCEPTED = "accepted", _("acceptée")
    ACCEPTED_MINOR = "accepted_minor", _("acceptée sous réserve de corrections")
    WAITLIST = "waitlist", _("liste d'attente")
    REJECTED = "rejected", _("rejetée")
    REVISION_REQUESTED = "revision_requested", _("corrections demandées")
    CAMERA_READY_RECEIVED = "camera_ready_received", _("version finale reçue")
    CONFIRMED = "confirmed", _("présentation confirmée")
    SCHEDULED = "scheduled", _("programmée")
    PRESENTED = "presented", _("présentée")
    PUBLISHED = "published", _("publiée dans les actes")
    WITHDRAWN = "withdrawn", _("retirée")


def reference_scope(edition: Any) -> str:
    """Portée du compteur des références d'une édition (par identifiant : le code peut
    changer jusqu'à la première soumission, RG-19)."""
    return f"submission:{edition.pk}"


class Submission(TimeStampedModel):
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="submissions",
    )
    # Attribuée à la première soumission définitive (F4) ; NULL en brouillon. MariaDB
    # traite les NULL comme distincts : l'unicité simple suffit (pas de contrainte
    # conditionnelle).
    reference = models.CharField(_("référence"), max_length=20, null=True, blank=True, unique=True)
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("soumissionnaire"),
        on_delete=models.RESTRICT,
        related_name="submissions",
    )
    track = models.ForeignKey(
        "conferences.Track",
        verbose_name=_("thématique"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="submissions",
    )
    submission_type = models.ForeignKey(
        "conferences.SubmissionType",
        verbose_name=_("type de communication"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="submissions",
    )
    language = models.CharField(_("langue"), max_length=2, blank=True, default="")
    title = models.CharField(_("titre"), max_length=300, blank=True, default="")
    # Titre normalisé (casse, accents, ponctuation), tenu à jour par les services : sert à
    # signaler les doublons d'un même soumissionnaire (F15) sans calcul à la lecture.
    title_key = models.CharField(_("titre normalisé"), max_length=300, blank=True, default="")
    abstract = models.TextField(_("résumé"), blank=True, default="")
    keywords = models.JSONField(_("mots-clés"), default=list, blank=True)
    status = models.CharField(
        _("statut"),
        max_length=24,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.DRAFT,
    )
    submitted_at = models.DateTimeField(_("soumise le"), null=True, blank=True)
    withdrawn_at = models.DateTimeField(_("retirée le"), null=True, blank=True)
    withdraw_reason = models.TextField(_("motif du retrait"), blank=True, default="")
    # Compteur d'écritures, contrôlé par If-Match contre les écritures concurrentes
    # (deux onglets, plan §4).
    revision = models.PositiveIntegerField(_("révision"), default=0)
    # Déclarations (F7) : {code: {"accepted": bool, "text_version": str}}.
    declarations = models.JSONField(_("déclarations"), default=dict, blank=True)

    # Champs journalisés avant/après : métadonnées sans donnée personnelle (le résumé et
    # le titre ne contiennent pas d'adresse ; les auteurs sont journalisés à part).
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "reference",
        "track",
        "submission_type",
        "language",
        "title",
        "status",
    )

    class Meta:
        verbose_name = _("soumission")
        verbose_name_plural = _("soumissions")
        indexes = (
            models.Index(fields=["edition", "status"], name="sub_edition_status"),
            models.Index(fields=["edition", "submitter", "title_key"], name="sub_title_key"),
        )

    def __str__(self) -> str:
        return self.reference or f"brouillon-{self.pk}"


class SubmissionAuthor(models.Model):
    """Auteur figé dans la soumission (étude §8.2 : nom et adresse dupliqués pour garder
    l'état au moment de la soumission). ``user`` : compte rattaché, quand l'adresse vérifiée
    correspond (F5)."""

    submission = models.ForeignKey(
        Submission, verbose_name=_("soumission"), on_delete=models.CASCADE, related_name="authors"
    )
    position = models.PositiveSmallIntegerField(_("ordre"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="authorships",
    )
    first_name = models.CharField(_("prénom"), max_length=150)
    last_name = models.CharField(_("nom"), max_length=150)
    email = models.EmailField(_("adresse e-mail"))
    institution = models.CharField(_("institution"), max_length=255, blank=True, default="")
    country = models.CharField(_("pays"), max_length=2, blank=True, default="")
    is_corresponding = models.BooleanField(_("auteur correspondant"), default=False)
    is_presenter = models.BooleanField(_("auteur présentateur"), default=False)

    class Meta:
        verbose_name = _("auteur")
        verbose_name_plural = _("auteurs")
        ordering = ("position", "id")
        constraints = (
            models.UniqueConstraint(fields=["submission", "position"], name="sub_author_position"),
            models.UniqueConstraint(fields=["submission", "email"], name="sub_author_email"),
        )

    def __str__(self) -> str:
        return f"{self.submission_id}#{self.position}"


class SubmissionFileKind(models.TextChoices):
    MAIN = "main", _("fichier principal")
    CAMERA_READY = "camera_ready", _("version finale")


class SubmissionFile(TimeStampedModel):
    """Fichier déposé, versionné, jamais écrasé (F3). Un seul fichier courant par nature :
    garanti par le service (pas de contrainte conditionnelle sous MariaDB) et contrôlé par
    ``check_integrity``."""

    submission = models.ForeignKey(
        Submission, verbose_name=_("soumission"), on_delete=models.RESTRICT, related_name="files"
    )
    kind = models.CharField(_("nature"), max_length=16, choices=SubmissionFileKind.choices)
    version = models.PositiveSmallIntegerField(_("version"))
    storage_name = models.CharField(_("nom de stockage"), max_length=64, unique=True)
    original_name = models.CharField(_("nom d'origine"), max_length=255)
    size = models.PositiveIntegerField(_("taille (octets)"))
    sha256 = models.CharField(_("empreinte SHA-256"), max_length=64)
    pages = models.PositiveIntegerField(_("pages"))
    metadata_removed = models.BooleanField(_("métadonnées retirées"), default=False)
    is_current = models.BooleanField(_("courant"), default=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("déposé par"),
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("fichier de soumission")
        verbose_name_plural = _("fichiers de soumission")
        constraints = (
            models.UniqueConstraint(
                fields=["submission", "kind", "version"], name="sub_file_version"
            ),
        )

    def __str__(self) -> str:
        return f"{self.submission_id}:{self.kind}:v{self.version}"


class SubmissionRevision(AppendOnlyModel):
    """Révision d'une soumission déjà soumise (F3) : cliché des métadonnées, des auteurs et
    du fichier courant, à chaque modification avant la clôture."""

    submission = models.ForeignKey(
        Submission,
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="revisions",
    )
    number = models.PositiveIntegerField(_("numéro"))
    at = models.DateTimeField(_("date"))
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    snapshot = models.JSONField(_("cliché"))

    @classmethod
    def redact(cls, submission_ids: list[int], scrub: Any) -> int:
        """Réécrit les clichés (anonymisation d'un auteur, plan L3 F16) : seule
        modification permise de cette table en ajout seul."""
        count = 0
        for revision in cls.objects.filter(submission_id__in=submission_ids):
            cleaned = scrub(revision.snapshot)
            if cleaned != revision.snapshot:
                cls.objects.filter(pk=revision.pk)._unchecked_update(snapshot=cleaned)
                count += 1
        return count

    class Meta:
        verbose_name = _("révision de soumission")
        verbose_name_plural = _("révisions de soumission")
        ordering = ("number",)
        constraints = (
            models.UniqueConstraint(fields=["submission", "number"], name="sub_revision_number"),
        )


class StatusHistory(AppendOnlyModel):
    """Historique des statuts (étude §8.2), écrit par ``workflow.transition`` seul."""

    submission = models.ForeignKey(
        Submission,
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="status_history",
    )
    from_status = models.CharField(
        _("statut précédent"), max_length=24, choices=SubmissionStatus.choices
    )
    to_status = models.CharField(
        _("nouveau statut"), max_length=24, choices=SubmissionStatus.choices
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    actor_label = models.CharField(_("libellé de l'acteur"), max_length=64, blank=True, default="")
    reason = models.TextField(_("motif"), blank=True, default="")
    at = models.DateTimeField(_("date"))

    @classmethod
    def redact(cls, submission_ids: list[int], scrub: Any) -> int:
        """Réécrit les motifs (anonymisation d'un auteur, plan L3 F16)."""
        count = 0
        for entry in cls.objects.filter(submission_id__in=submission_ids).exclude(reason=""):
            cleaned = scrub(entry.reason)
            if cleaned != entry.reason:
                cls.objects.filter(pk=entry.pk)._unchecked_update(reason=cleaned)
                count += 1
        return count

    class Meta:
        verbose_name = _("historique de statut")
        verbose_name_plural = _("historiques de statut")
        ordering = ("at", "id")


class SubmissionExtension(TimeStampedModel):
    """Dérogation après clôture (RG-02, F8), par soumission, avec échéance et motif."""

    submission = models.ForeignKey(
        Submission,
        verbose_name=_("soumission"),
        on_delete=models.RESTRICT,
        related_name="extensions",
    )
    until = models.DateTimeField(_("échéance (UTC)"))
    reason = models.TextField(_("motif"))
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("accordée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    granted_at = models.DateTimeField(_("accordée le"))
    revoked_at = models.DateTimeField(_("révoquée le"), null=True, blank=True)

    class Meta:
        verbose_name = _("dérogation")
        verbose_name_plural = _("dérogations")
        ordering = ("-granted_at", "-id")
        constraints = (
            models.CheckConstraint(condition=~Q(reason=""), name="sub_extension_reason"),
        )


class ReminderKind(models.TextChoices):
    """Rappels des brouillons avant la clôture de l'appel (F13, étude A2)."""

    SEVEN_DAYS = "j7", _("sept jours avant la clôture")
    ONE_DAY = "j1", _("la veille de la clôture")


class DraftReminder(models.Model):
    """Rappel envoyé pour un brouillon : la contrainte d'unicité rend l'envoi idempotent
    (un cron relancé ou chevauchant n'envoie pas deux fois). Supprimé avec le brouillon
    (``CASCADE`` : la ligne n'a aucune valeur sans lui, et un brouillon se supprime)."""

    submission = models.ForeignKey(
        Submission,
        verbose_name=_("soumission"),
        on_delete=models.CASCADE,
        related_name="reminders",
    )
    kind = models.CharField(_("rappel"), max_length=4, choices=ReminderKind.choices)
    sent_at = models.DateTimeField(_("envoyé le"))

    class Meta:
        verbose_name = _("rappel de brouillon")
        verbose_name_plural = _("rappels de brouillon")
        constraints = (
            models.UniqueConstraint(fields=["submission", "kind"], name="sub_reminder_once"),
        )

    def __str__(self) -> str:
        return f"{self.submission_id}:{self.kind}"
