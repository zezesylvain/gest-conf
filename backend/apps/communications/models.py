"""Registre des e-mails envoyés (plan L1 §3.6 et §8.1).

``OutboxEmail`` n'est pas une seconde file : chaque e-mail est envoyé par un job
``communications.send_email`` de la file unique (``apps.core.jobs``). La table
sert de journal d'envoi, de base aux statistiques d'échec et à l'anonymisation.
La clé étrangère vers ``Edition`` est ajoutée en L1.5 (``communications/0002``).
"""

from django.conf import settings
from django.db import models
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
    """Notifications dans l'application (plan L3, F13). Lot L3 : soumissions."""

    SUBMISSION_RECEIVED = "submission_received", _("soumission reçue")
    SUBMISSION_WITHDRAWN = "submission_withdrawn", _("soumission retirée")
    COAUTHOR_ADDED = "coauthor_added", _("déclaré co-auteur")
    EXTENSION_GRANTED = "extension_granted", _("dérogation accordée")
    DRAFT_REMINDER = "draft_reminder", _("brouillon à soumettre")


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
