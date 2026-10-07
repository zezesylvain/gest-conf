"""Registre des e-mails envoyés (plan L1 §3.6 et §8.1).

``OutboxEmail`` n'est pas une seconde file : chaque e-mail est envoyé par un job
``communications.send_email`` de la file unique (``apps.core.jobs``). La table
sert de journal d'envoi, de base aux statistiques d'échec et à l'anonymisation.
La clé étrangère vers ``Edition`` est ajoutée en L1.5 (``communications/0002``).
"""

from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.models import TimeStampedModel


class OutboxStatus(models.TextChoices):
    QUEUED = "queued", _("en file")
    SENDING = "sending", _("en cours d'envoi")
    SENT = "sent", _("envoyé")
    FAILED = "failed", _("en échec")
    CANCELLED = "cancelled", _("annulé")


class OutboxEmail(TimeStampedModel):
    """Un e-mail, rendu pendant la requête dans la langue du destinataire.

    Rendu dans la requête : hors requête (cron), allauth ne sait pas construire
    les URL (plan §3.6). L'objet ne contient aucune donnée de personne (règle des
    gabarits, §8.3). Le corps d'un e-mail ``is_sensitive`` (lien à jeton) est
    purgé dès l'envoi : sinon, un simple accès en lecture à la base suffirait
    pour réinitialiser un mot de passe ou accepter une invitation.
    """

    to_email = models.EmailField(_("destinataire"), db_index=True)
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte destinataire"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    template_code = models.CharField(_("gabarit"), max_length=64)
    locale = models.CharField(_("langue"), max_length=8)
    subject = models.CharField(_("objet"), max_length=255)
    body_text = models.TextField(_("corps (texte)"), blank=True, default="")
    body_html = models.TextField(_("corps (HTML)"), blank=True, default="")
    is_sensitive = models.BooleanField(_("contient un lien à jeton"), default=False)
    # Envoi groupé (plan L8, N11) : n'use que la moitié du plafond horaire.
    is_bulk = models.BooleanField(_("envoi groupé"), default=False)
    status = models.CharField(
        _("statut"), max_length=10, choices=OutboxStatus.choices, default=OutboxStatus.QUEUED
    )
    attempts = models.PositiveSmallIntegerField(_("tentatives"), default=0)
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")
    scheduled_at = models.DateTimeField(_("programmé le"))
    sent_at = models.DateTimeField(_("envoyé le"), null=True, blank=True)
    purged_at = models.DateTimeField(_("corps purgé le"), null=True, blank=True)
    provider_message_id = models.CharField(
        _("identifiant chez le fournisseur"), max_length=255, blank=True, default=""
    )
    # Clé d'unicité nullable (plan L1 §3.1) : NULL quand aucune déduplication n'est voulue.
    idempotency_key = models.CharField(
        _("clé d'idempotence"), max_length=128, null=True, blank=True, unique=True
    )

    class Meta:
        verbose_name = _("e-mail envoyé")
        verbose_name_plural = _("e-mails envoyés")
        indexes = (
            models.Index(fields=["status", "scheduled_at"], name="comm_outbox_status"),
            models.Index(fields=["to_user", "created_at"], name="comm_outbox_user"),
        )

    def __str__(self) -> str:
        return f"{self.template_code}#{self.pk} ({self.status})"


class NotificationKind(models.TextChoices):
    """Notifications dans l'application (plan L3, F13). Lot L3 : soumissions ; lot L4 :
    recevabilité, décisions, version finale ; lot L8 : tâche confiée (N3), poste de
    bénévolat confié ou retiré (N9), annonce (N10), questionnaire de satisfaction (N12)."""

    SUBMISSION_RECEIVED = "submission_received", _("soumission reçue")
    SUBMISSION_WITHDRAWN = "submission_withdrawn", _("soumission retirée")
    COAUTHOR_ADDED = "coauthor_added", _("déclaré co-auteur")
    EXTENSION_GRANTED = "extension_granted", _("dérogation accordée")
    DRAFT_REMINDER = "draft_reminder", _("brouillon à soumettre")
    SCREENING_REJECTED = "screening_rejected", _("soumission non recevable")
    DECISION_PUBLISHED = "decision_published", _("décision publiée")
    FINAL_VERSION_RECEIVED = "final_version_received", _("version finale reçue")
    TASK_ASSIGNED = "task_assigned", _("tâche confiée")
    SHIFT_ASSIGNED = "shift_assigned", _("poste de bénévolat confié")
    SHIFT_REMOVED = "shift_removed", _("poste de bénévolat retiré")
    ANNOUNCEMENT = "announcement", _("annonce")
    SURVEY_INVITATION = "survey_invitation", _("questionnaire de satisfaction")


class Notification(TimeStampedModel):
    """Notification de la cloche (plan L3, F13), doublée d'un e-mail quand il y en a un.

    Le texte n'est pas stocké : l'interface le compose à partir de ``kind`` et de
    ``payload`` (clés de traduction), dans la langue courante. ``payload`` ne contient que
    des éléments de l'objet visé (référence, titre, échéance), jamais de donnée d'un tiers.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    kind = models.CharField(_("nature"), max_length=32, choices=NotificationKind.choices)
    payload = models.JSONField(_("données"), default=dict, blank=True)
    read_at = models.DateTimeField(_("lue le"), null=True, blank=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ("-created_at", "-id")
        indexes = (models.Index(fields=["user", "read_at"], name="comm_notification_unread"),)


# --- Annonces et envois groupés (plan L8, N10 et N11) -------------------------------------


class AnnouncementStatus(models.TextChoices):
    DRAFT = "draft", _("brouillon")
    PUBLISHED = "published", _("publiée")
    WITHDRAWN = "withdrawn", _("retirée")


class SendingStatus(models.TextChoices):
    """Mise en file de la cloche et des e-mails d'une annonce (les e-mails partent ensuite,
    étalés, par ``run_jobs``)."""

    NONE = "none", _("aucun envoi")
    QUEUING = "queuing", _("mise en file")
    QUEUED = "queued", _("en file d'envoi")
    CANCELLED = "cancelled", _("annulé")


class Announcement(TimeStampedModel):
    """Annonce d'une édition (N10) : actualités du portail, bandeau de dernière minute,
    cloche et e-mail aux destinataires d'un segment (N11, RG-22).

    ``body_fr`` et ``body_en`` : HTML assaini par la liste blanche de L2. Le bandeau ne porte
    que du texte. Compteurs de l'envoi tenus par la mise en file (``fan_out_cursor`` : dernier
    compte traité, dans l'ordre des identifiants)."""

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="announcements",
    )
    title_fr = models.CharField(_("titre (FR)"), max_length=150)
    title_en = models.CharField(_("titre (EN)"), max_length=150, blank=True, default="")
    body_fr = models.TextField(_("texte (FR)"), blank=True, default="")
    body_en = models.TextField(_("texte (EN)"), blank=True, default="")
    on_news = models.BooleanField(_("actualités"), default=False)
    on_banner = models.BooleanField(_("bandeau"), default=False)
    on_bell = models.BooleanField(_("cloche"), default=False)
    by_email = models.BooleanField(_("e-mail"), default=False)
    segment = models.CharField(_("segment"), max_length=64, blank=True, default="")
    banner_message_fr = models.CharField(
        _("message du bandeau (FR)"), max_length=280, blank=True, default=""
    )
    banner_message_en = models.CharField(
        _("message du bandeau (EN)"), max_length=280, blank=True, default=""
    )
    banner_starts_at = models.DateTimeField(_("début du bandeau"), null=True, blank=True)
    banner_ends_at = models.DateTimeField(_("fin du bandeau"), null=True, blank=True)
    status = models.CharField(
        _("statut"),
        max_length=10,
        choices=AnnouncementStatus.choices,
        default=AnnouncementStatus.DRAFT,
    )
    published_at = models.DateTimeField(_("publiée le"), null=True, blank=True)
    withdrawn_at = models.DateTimeField(_("retirée le"), null=True, blank=True)
    sending_status = models.CharField(
        _("envoi"), max_length=10, choices=SendingStatus.choices, default=SendingStatus.NONE
    )
    recipients_count = models.PositiveIntegerField(_("destinataires comptés"), default=0)
    delivered_count = models.PositiveIntegerField(_("destinataires traités"), default=0)
    emails_count = models.PositiveIntegerField(_("e-mails mis en file"), default=0)
    fan_out_cursor = models.PositiveBigIntegerField(_("curseur de mise en file"), default=0)
    sending_started_at = models.DateTimeField(_("envoi commencé le"), null=True, blank=True)
    sending_finished_at = models.DateTimeField(_("envoi arrêté le"), null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("créée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    class Meta:
        verbose_name = _("annonce")
        verbose_name_plural = _("annonces")
        ordering = ("-created_at", "-id")
        indexes = (models.Index(fields=["edition", "status"], name="comm_announcement_status"),)
        constraints = (
            models.CheckConstraint(
                condition=Q(banner_starts_at__isnull=True)
                | Q(banner_ends_at__isnull=True)
                | Q(banner_ends_at__gt=F("banner_starts_at")),
                name="comm_announcement_banner_order",
            ),
        )

    def __str__(self) -> str:
        return self.title_fr


class AnnouncementDelivery(models.Model):
    """Destinataire d'une annonce (N11) : traçabilité sans liste en copie ; la mise en file
    s'appuie dessus pour rester rejouable sans doublon."""

    announcement = models.ForeignKey(
        Announcement,
        verbose_name=_("annonce"),
        on_delete=models.RESTRICT,
        related_name="deliveries",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("destinataire"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    emailed = models.BooleanField(_("e-mail mis en file"), default=False)
    delivered_at = models.DateTimeField(_("traité le"), default=timezone.now)

    class Meta:
        verbose_name = _("destinataire d'une annonce")
        verbose_name_plural = _("destinataires des annonces")
        constraints = (
            models.UniqueConstraint(fields=("announcement", "user"), name="comm_delivery_unique"),
        )

    def __str__(self) -> str:
        return f"{self.announcement_id}:{self.user_id}"


class AnnouncementOptOut(models.Model):
    """Désabonnement des annonces d'une édition (N11) : les e-mails de service restent
    envoyés."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="+",
    )
    created_at = models.DateTimeField(_("désabonné le"), default=timezone.now)

    class Meta:
        verbose_name = _("désabonnement des annonces")
        verbose_name_plural = _("désabonnements des annonces")
        constraints = (
            models.UniqueConstraint(fields=("user", "edition"), name="comm_opt_out_unique"),
        )

    def __str__(self) -> str:
        return f"{self.user_id}:{self.edition_id}"
