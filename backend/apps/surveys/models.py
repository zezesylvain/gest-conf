"""Questionnaires de satisfaction (plan L8 §3, N12 ; étude M14, annexe A2) : questions,
invitations des présents et réponses **anonymes** (RG-21).

**RG-21** : une réponse est stockée **sans lien** avec la personne qui répond ni avec son
invitation ; sa clé est **aléatoire** (UUID), pour que l'ordre d'insertion ne se lise pas
dans la table ; elle ne porte **aucune date**. L'invitation ne garde que le jour de la
réponse, sans horodatage précis (pas de ``TimeStampedModel``). Un jour gardé des deux côtés
aurait suffi à rapprocher la réponse de la seule personne qui a répondu ce jour-là.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class SurveyScope(models.TextChoices):
    GLOBAL = "global", _("conférence")
    SESSION = "session", _("session")


class SurveyStatus(models.TextChoices):
    DRAFT = "draft", _("brouillon")
    PUBLISHED = "published", _("publié")


class QuestionKind(models.TextChoices):
    RATING = "rating", _("note de 1 à 5")
    SINGLE = "single", _("choix unique")
    MULTIPLE = "multiple", _("choix multiples")
    TEXT = "text", _("texte libre")


class Survey(TimeStampedModel):
    """Questionnaire de l'édition, global ou d'une session. Ouvert entre ``opens_at`` et
    ``closes_at`` une fois publié ; **verrouillé** à la première réponse (``locked_at``) :
    ses questions ne changent plus, on le duplique (comme une grille, RG-05)."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="surveys",
    )
    scope = models.CharField(
        _("portée"), max_length=8, choices=SurveyScope.choices, default=SurveyScope.GLOBAL
    )
    session = models.ForeignKey(
        "program.Session",
        verbose_name=_("session"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    title_fr = models.CharField(_("titre (FR)"), max_length=150)
    title_en = models.CharField(_("titre (EN)"), max_length=150, blank=True, default="")
    intro_fr = models.TextField(_("introduction (FR)"), blank=True, default="")
    intro_en = models.TextField(_("introduction (EN)"), blank=True, default="")
    opens_at = models.DateTimeField(_("ouverture"), null=True, blank=True)
    closes_at = models.DateTimeField(_("clôture"), null=True, blank=True)
    status = models.CharField(
        _("statut"), max_length=10, choices=SurveyStatus.choices, default=SurveyStatus.DRAFT
    )
    published_at = models.DateTimeField(_("publié le"), null=True, blank=True)
    locked_at = models.DateTimeField(_("verrouillé le"), null=True, blank=True)
    invite_cursor = models.PositiveBigIntegerField(_("curseur des invitations"), default=0)
    invitations_done = models.BooleanField(_("invitations envoyées"), default=False)
    remind_cursor = models.PositiveBigIntegerField(_("curseur de la relance"), default=0)
    reminders_done = models.BooleanField(_("relance envoyée"), default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créé par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("questionnaire")
        verbose_name_plural = _("questionnaires")
        ordering = ("-created_at", "-id")
        constraints = (
            models.CheckConstraint(
                condition=Q(opens_at__isnull=True)
                | Q(closes_at__isnull=True)
                | Q(closes_at__gt=F("opens_at")),
                name="srv_survey_dates",
            ),
            models.CheckConstraint(
                condition=Q(scope="global", session__isnull=True)
                | Q(scope="session", session__isnull=False),
                name="srv_survey_scope",
            ),
        )

    def __str__(self) -> str:
        return self.title_fr


class SurveyQuestion(models.Model):
    """Question d'un questionnaire ; ``choices`` : liste de ``{"value", "label_fr",
    "label_en"}`` pour les choix unique et multiples."""

    survey = models.ForeignKey(
        Survey, verbose_name=_("questionnaire"), on_delete=models.CASCADE, related_name="questions"
    )
    position = models.PositiveSmallIntegerField(_("position"), default=0)
    kind = models.CharField(_("type"), max_length=8, choices=QuestionKind.choices)
    label_fr = models.CharField(_("libellé (FR)"), max_length=300)
    label_en = models.CharField(_("libellé (EN)"), max_length=300, blank=True, default="")
    choices = models.JSONField(_("choix"), default=list, blank=True)
    required = models.BooleanField(_("obligatoire"), default=False)

    class Meta:
        verbose_name = _("question")
        verbose_name_plural = _("questions")
        ordering = ("survey", "position", "id")

    def __str__(self) -> str:
        return self.label_fr


class SurveyInvitation(models.Model):
    """Invitation d'une personne présente (N12). Dates **au jour** seulement (RG-21) : pas de
    ``created_at`` ni d'``updated_at`` qui donneraient l'heure de la réponse."""

    survey = models.ForeignKey(
        Survey,
        verbose_name=_("questionnaire"),
        on_delete=models.RESTRICT,
        related_name="invitations",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("personne invitée"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    invited_on = models.DateField(_("invitée le"))
    reminded_on = models.DateField(_("relancée le"), null=True, blank=True)
    answered_on = models.DateField(_("répondu le"), null=True, blank=True)

    class Meta:
        verbose_name = _("invitation à un questionnaire")
        verbose_name_plural = _("invitations aux questionnaires")
        constraints = (
            models.UniqueConstraint(fields=("survey", "user"), name="srv_invitation_unique"),
        )

    def __str__(self) -> str:
        return f"{self.survey_id}:{self.user_id}"


class SurveyResponse(models.Model):
    """Réponse anonyme (RG-21) : aucune clé vers un compte ni vers l'invitation, clé
    aléatoire, aucune date. ``answers`` : ``{identifiant de question: valeur}``."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    survey = models.ForeignKey(
        Survey, verbose_name=_("questionnaire"), on_delete=models.RESTRICT, related_name="responses"
    )
    answers = models.JSONField(_("réponses"), default=dict)

    class Meta:
        verbose_name = _("réponse à un questionnaire")
        verbose_name_plural = _("réponses aux questionnaires")

    def __str__(self) -> str:
        return str(self.id)
