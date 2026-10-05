"""Modèles transverses : horodatage, journal d'audit, file de tâches, battements de cœur.

Plan L1 §3.5. Les clés étrangères vers ``Edition`` (``AuditLog.edition``,
``Job.edition``) sont arrivées en L1.5 avec l'application ``conferences``, par une
migration additive (``core/0002``, plan §3.8).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NoReturn

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.actor import LABEL_MAX_LENGTH, USER_AGENT_MAX_LENGTH, ActorKind


class TimeStampedModel(models.Model):
    """Base de toutes les tables métier : horodatage de création et de mise à jour (étude §8.2)."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# --- Journal d'audit (RG-17) -------------------------------------------------------------


class AppendOnlyError(Exception):
    """Modification ou suppression refusée sur une table en ajout seul (plan L1 §7.1)."""


class AppendOnlyQuerySet(models.QuerySet):
    """Refuse ``update()`` et ``delete()`` en masse.

    Les seules modifications autorisées passent par des méthodes nommées du
    modèle, elles-mêmes auditées, qui appellent ``_unchecked_update`` ou
    ``_unchecked_delete``.
    """

    def update(self, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError(f"{self.model._meta.label} : table en ajout seul (update refusé).")

    def delete(self) -> NoReturn:
        raise AppendOnlyError(f"{self.model._meta.label} : table en ajout seul (delete refusé).")

    def _unchecked_update(self, **kwargs: Any) -> int:
        return super().update(**kwargs)

    def _unchecked_delete(self) -> int:
        deleted, _per_model = super().delete()
        return deleted


class AppendOnlyModel(models.Model):
    """Ligne écrite une fois, jamais modifiée ni supprimée hors méthodes nommées."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError(f"{self._meta.label} : table en ajout seul (save refusé).")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError(f"{self._meta.label} : table en ajout seul (delete refusé).")


class AuditLog(AppendOnlyModel):
    """Journal d'audit (RG-17, étude §8.2, plan L1 §3.5 et §7).

    Écrit par ``apps.core.audit.record`` dans la transaction du service métier.
    ``before`` et ``after`` ne contiennent que des champs en liste blanche
    (``AUDIT_FIELDS``) : jamais de mot de passe, de secret, de jeton ni d'adresse
    e-mail en clair. ``actor_label`` ne sert qu'aux commandes et aux tâches.
    """

    at = models.DateTimeField(_("date"), db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    actor_kind = models.CharField(_("type d'acteur"), max_length=8, choices=ActorKind.choices)
    # Ajout par rapport à l'étude §8.2 (B8) : limite la lecture d'un président à son édition.
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    actor_label = models.CharField(
        _("libellé de l'acteur"), max_length=LABEL_MAX_LENGTH, blank=True, default=""
    )
    action = models.CharField(_("action"), max_length=64)
    object_type = models.CharField(_("type d'objet"), max_length=64, blank=True, default="")
    object_id = models.CharField(_("identifiant d'objet"), max_length=64, blank=True, default="")
    before = models.JSONField(_("avant"), null=True, blank=True)
    after = models.JSONField(_("après"), null=True, blank=True)
    reason = models.TextField(_("motif"), blank=True, default="")
    request_id = models.CharField(
        _("identifiant de requête"), max_length=32, blank=True, default=""
    )
    ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    user_agent = models.CharField(
        _("navigateur"), max_length=USER_AGENT_MAX_LENGTH, blank=True, default=""
    )

    class Meta:
        verbose_name = _("entrée du journal d'audit")
        verbose_name_plural = _("journal d'audit")
        ordering = ("-at", "-id")
        indexes = (
            models.Index(fields=["edition", "at"], name="core_audit_edition_at"),
            models.Index(fields=["actor", "at"], name="core_audit_actor_at"),
            models.Index(fields=["object_type", "object_id"], name="core_audit_object"),
            models.Index(fields=["action", "at"], name="core_audit_action_at"),
        )

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.action}"

    # Méthodes nommées, seules autorisées à modifier la table (plan L1 §7.1). Chacune
    # écrit sa propre entrée d'audit, non concernée par l'opération qu'elle décrit.

    @classmethod
    def purge_network_before(cls, date: datetime, *, actor: Any) -> int:
        """Efface l'IP et le user-agent des entrées antérieures à ``date`` (D15 : 6 mois)."""
        from apps.core.audit import record

        count = (
            cls.objects.filter(at__lt=date)
            .exclude(ip__isnull=True, user_agent="")
            ._unchecked_update(ip=None, user_agent="")
        )
        record("audit.network_purged", actor=actor, after={"before": date, "count": count})
        return count

    @classmethod
    def purge_before(cls, date: datetime, *, actor: Any) -> int:
        """Supprime les entrées antérieures à ``date`` (D15 : 3 ans)."""
        from apps.core.audit import record

        count = cls.objects.filter(at__lt=date)._unchecked_delete()
        record("audit.purged", actor=actor, after={"before": date, "count": count})
        return count

    @classmethod
    def redact_network_for_user(cls, user: Any, *, actor: Any) -> int:
        """Efface l'IP et le user-agent des actions d'un compte (anonymisation, plan §4.9)."""
        from apps.core.audit import record

        count = (
            cls.objects.filter(actor=user)
            .exclude(ip__isnull=True, user_agent="")
            ._unchecked_update(ip=None, user_agent="")
        )
        record(
            "audit.network_redacted",
            actor=actor,
            obj=user,
            after={"count": count},
        )
        return count


# --- File de tâches (règle n° 9) -----------------------------------------------------------


class JobStatus(models.TextChoices):
    PENDING = "pending", _("en attente")
    RUNNING = "running", _("en cours")
    SUCCEEDED = "succeeded", _("terminée")
    FAILED = "failed", _("en échec")
    CANCELLED = "cancelled", _("annulée")


class JobPriority(models.IntegerChoices):
    """Ordre de traitement par le cron (plus petit = plus tôt, plan L1 §3.5)."""

    URGENT = 0, _("urgente")  # e-mails de sécurité et de la voie rapide
    NORMAL = 100, _("normale")
    BULK = 200, _("envoi de masse")


class Job(TimeStampedModel):
    """Tâche asynchrone exécutée par ``manage.py run_jobs`` (cron), plan L1 §3.5 et §8.2.

    ``payload`` ne contient que des identifiants et des scalaires, jamais de
    secret. Livraison « au moins une fois » : chaque gestionnaire est idempotent.
    """

    kind = models.CharField(_("type"), max_length=64)
    payload = models.JSONField(_("données"), default=dict, blank=True)
    status = models.CharField(
        _("statut"), max_length=10, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    priority = models.SmallIntegerField(_("priorité"), default=JobPriority.NORMAL)
    run_at = models.DateTimeField(_("à exécuter à partir de"))
    attempts = models.PositiveSmallIntegerField(_("tentatives"), default=0)
    max_attempts = models.PositiveSmallIntegerField(_("tentatives maximales"), default=5)
    locked_at = models.DateTimeField(_("réservée le"), null=True, blank=True)
    locked_by = models.CharField(_("réservée par"), max_length=64, blank=True, default="")
    finished_at = models.DateTimeField(_("terminée le"), null=True, blank=True)
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")
    # Clé d'unicité nullable (plan L1 §3.1) : NULL quand aucune déduplication n'est voulue.
    dedup_key = models.CharField(
        _("clé d'idempotence"), max_length=128, null=True, blank=True, unique=True
    )

    class Meta:
        verbose_name = _("tâche")
        verbose_name_plural = _("tâches")
        indexes = (models.Index(fields=["status", "priority", "run_at"], name="core_job_queue"),)

    def __str__(self) -> str:
        return f"{self.kind}#{self.pk} ({self.status})"


class HeartbeatStatus(models.TextChoices):
    RUNNING = "running", _("en cours")
    OK = "ok", _("réussi")
    ERROR = "error", _("en erreur")


class CronHeartbeat(models.Model):
    """Dernier passage de chaque commande cron (supervision, ``/health``), plan L1 §3.5."""

    name = models.CharField(_("commande"), max_length=64, unique=True)
    last_started_at = models.DateTimeField(_("dernier démarrage"), null=True, blank=True)
    last_finished_at = models.DateTimeField(_("dernière fin"), null=True, blank=True)
    last_success_at = models.DateTimeField(_("dernier succès"), null=True, blank=True)
    last_status = models.CharField(
        _("dernier statut"), max_length=10, choices=HeartbeatStatus.choices, blank=True
    )
    last_duration_ms = models.PositiveIntegerField(_("dernière durée (ms)"), null=True, blank=True)
    processed_count = models.PositiveIntegerField(_("éléments traités"), default=0)
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")

    class Meta:
        verbose_name = _("battement de cœur")
        verbose_name_plural = _("battements de cœur")

    def __str__(self) -> str:
        return f"{self.name} ({self.last_status})"


class PublicFileKind(models.TextChoices):
    DOCUMENT = "document", _("document")
    IMAGE = "image", _("image")
    PHOTO = "photo", _("photo de profil")


class PublicFile(TimeStampedModel):
    """Fichier **public par nature** (E4, plan L2) : modèle de document, image de section,
    affiche, photo de profil.

    Stocké hors de la racine web sous un nom aléatoire, type vérifié par son contenu, images
    réencodées sans métadonnées ; servi par ``GET /v1/public/files/<uuid>/<nom>`` seulement
    s'il est publié et que son contexte le permet (édition publiée, consentement). Écrit et
    supprimé par ``apps.core.public_files`` uniquement.
    """

    uuid = models.UUIDField(_("identifiant public"), unique=True, editable=False)
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    kind = models.CharField(_("nature"), max_length=10, choices=PublicFileKind.choices)
    storage_name = models.CharField(_("nom de stockage"), max_length=80, unique=True)
    original_name = models.CharField(_("nom d'origine"), max_length=255)
    extension = models.CharField(_("extension"), max_length=8)
    content_type = models.CharField(_("type de contenu"), max_length=100)
    size = models.PositiveIntegerField(_("taille (octets)"))
    sha256 = models.CharField(_("empreinte SHA-256"), max_length=64)
    width = models.PositiveIntegerField(_("largeur"), null=True, blank=True)
    height = models.PositiveIntegerField(_("hauteur"), null=True, blank=True)
    title_fr = models.CharField(_("titre (FR)"), max_length=255, blank=True, default="")
    title_en = models.CharField(_("titre (EN)"), max_length=255, blank=True, default="")
    position = models.PositiveSmallIntegerField(_("ordre"), default=0)
    published = models.BooleanField(_("publié"), default=False)

    AUDIT_FIELDS = (
        "uuid",
        "kind",
        "original_name",
        "content_type",
        "size",
        "sha256",
        "title_fr",
        "title_en",
        "position",
        "published",
    )

    class Meta:
        verbose_name = _("fichier public")
        verbose_name_plural = _("fichiers publics")
        ordering = ("position", "id")
        indexes = (models.Index(fields=["edition", "kind", "position"], name="core_pubfile_kind"),)

    def __str__(self) -> str:
        return f"{self.kind}:{self.uuid}"
