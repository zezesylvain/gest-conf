"""Registre des e-mails (plan L1 §3.6, §8.1).

``OutboxEmail`` n'est pas une seconde file : l'envoi passe par un ``Job``
(``communications.send_email``). La table sert de journal d'envoi, de base aux
statistiques d'échec et à l'anonymisation. Sans colonne ``edition`` en L1.2 : elle
arrive en L1.5 par ``communications/0002`` (§3.8).
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.audit import mask_email
from apps.core.models import TimeStampedModel

SUBJECT_MAX_LENGTH = 255


class OutboxStatus(models.TextChoices):
    QUEUED = "queued", _("en file")
    SENDING = "sending", _("en cours d'envoi")
    SENT = "sent", _("envoyé")
    FAILED = "failed", _("en échec")
    CANCELLED = "cancelled", _("annulé")


class OutboxEmail(TimeStampedModel):
    """Un e-mail, rendu pendant la requête, puis envoyé par la file (plan §8.3)."""

    # Liste blanche du journal d'audit (apps.core.audit.snapshot) : ni l'adresse en clair,
    # ni l'objet, ni les corps.
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "template_code",
        "locale",
        "status",
        "attempts",
        "is_sensitive",
        "scheduled_at",
        "sent_at",
        "to_user",
        "to_email_masked",
    )

    # Remplacée par l'adresse anonymisée à l'anonymisation du destinataire (§4.9, L1.8).
    to_email = models.EmailField(_("destinataire"))
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("compte destinataire"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="outbox_emails",
    )
    template_code = models.CharField(_("gabarit"), max_length=64)
    locale = models.CharField(_("langue"), max_length=8)
    # Rendus pendant la requête (§3.6). L'objet ne contient aucune donnée de personne
    # (règle des gabarits, test test_subject_templates_have_no_personal_data).
    subject = models.CharField(_("objet"), max_length=SUBJECT_MAX_LENGTH)
    body_text = models.TextField(_("corps (texte)"), blank=True, default="")
    body_html = models.TextField(_("corps (HTML)"), blank=True, default="")
    # Liens de vérification, de réinitialisation, d'invitation : corps purgé dès l'envoi
    # (au plus 24 h en cas d'échec, apps.core.retention).
    is_sensitive = models.BooleanField(_("sensible"), default=False)
    status = models.CharField(
        _("statut"), max_length=10, choices=OutboxStatus.choices, default=OutboxStatus.QUEUED
    )
    attempts = models.PositiveSmallIntegerField(_("tentatives"), default=0)
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")
    scheduled_at = models.DateTimeField(_("prévu le"), default=timezone.now)
    sent_at = models.DateTimeField(_("envoyé le"), null=True, blank=True)
    purged_at = models.DateTimeField(_("corps purgé le"), null=True, blank=True)
    provider_message_id = models.CharField(
        _("identifiant chez le fournisseur"), max_length=255, blank=True, default=""
    )
    # Clé d'unicité nullable (plan L1 §3.1) : NULL = pas d'idempotence demandée.
    idempotency_key = models.CharField(
        _("clé d'idempotence"), max_length=128, null=True, blank=True, unique=True
    )

    class Meta:
        verbose_name = _("e-mail envoyé")
        verbose_name_plural = _("e-mails envoyés")
        indexes = (
            models.Index(fields=["status", "scheduled_at"], name="comm_outbox_status_idx"),
            models.Index(fields=["to_user", "created_at"], name="comm_outbox_user_idx"),
            # Anonymisation des envois sans compte (§4.9).
            models.Index(fields=["to_email"], name="comm_outbox_to_email_idx"),
            # Plafond global d'envoi par heure (§4.7) : comptage des envois récents.
            models.Index(fields=["sent_at"], name="comm_outbox_sent_at_idx"),
        )
        constraints = (
            models.CheckConstraint(
                condition=Q(status__in=OutboxStatus.values), name="comm_outbox_status_valid"
            ),
            models.CheckConstraint(
                condition=~Q(idempotency_key=""), name="comm_outbox_idempotency_key_not_blank"
            ),
        )

    def __str__(self) -> str:
        return f"{self.template_code} #{self.pk} ({self.status})"

    @property
    def to_email_masked(self) -> str:
        return mask_email(self.to_email)
