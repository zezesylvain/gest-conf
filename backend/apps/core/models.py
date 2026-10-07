"""Modèles du socle : horodatage commun, journal d'audit, file de tâches, battements de cœur.

Plan L1 §3.5 (sans colonne ``edition`` : elle arrive en L1.5 par ``core/0002``, §3.8).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.actor import LABEL_MAX_LENGTH, USER_AGENT_MAX_LENGTH, ActorKind

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser

    from apps.core.actor import Actor


class TimeStampedModel(models.Model):
    """Base de toutes les tables métier : horodatage de création et de mise à jour (étude §8.2)."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


def _choices_check(
    field: str, choices: type[models.TextChoices], name: str
) -> models.CheckConstraint:
    """Contrainte CHECK limitant une colonne aux valeurs d'une énumération (MariaDB la crée)."""
    return models.CheckConstraint(condition=Q(**{f"{field}__in": choices.values}), name=name)


# --- Journal d'audit (RG-17, plan L1 §7) ------------------------------------------------


class AppendOnlyError(RuntimeError):
    """Modification ou suppression refusée sur une table en ajout seul (plan L1 §7.1)."""


def _refuse(what: str) -> NoReturn:
    raise AppendOnlyError(
        f"{what} refusé : le journal d'audit est en ajout seul. Utiliser les méthodes nommées "
        "purge_network_before, purge_before ou redact_network_for_user."
    )


class AuditLogQuerySet(models.QuerySet):
    """Refuse ``update()``, ``bulk_update()`` et ``delete()`` : seules les méthodes nommées
    du gestionnaire modifient le journal."""

    def update(self, **kwargs: Any) -> NoReturn:
        _refuse("update()")

    def delete(self) -> NoReturn:
        _refuse("delete()")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> NoReturn:
        # Refus immédiat : l'implémentation de Django ouvrirait d'abord une transaction
        # (sans point de sauvegarde), que l'erreur de update() laisserait inutilisable.
        _refuse("bulk_update()")

    # Chemins privilégiés, réservés aux méthodes nommées (et auditées) d'AuditLogManager.
    def _privileged_update(self, **kwargs: Any) -> int:
        return super().update(**kwargs)

    def _privileged_delete(self) -> int:
        return super().delete()[0]


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):  # type: ignore[misc]
    """Les trois seules modifications autorisées du journal (plan L1 §7.1, D15).

    Chacune est elle-même journalisée, dans la même transaction, et porte sur tout le
    journal (jamais sur un queryset filtré par l'appelant).
    """

    def purge_network_before(self, cutoff: datetime, *, actor: Actor) -> int:
        """Efface l'IP et le user-agent des lignes antérieures à ``cutoff`` (6 mois, D15)."""
        from apps.core.audit import AuditAction, record

        with transaction.atomic():
            count = (
                self.get_queryset()
                .filter(at__lt=cutoff)
                .filter(Q(ip__isnull=False) | ~Q(user_agent=""))
                ._privileged_update(ip=None, user_agent="")
            )
            record(
                AuditAction.AUDIT_NETWORK_PURGED,
                actor=actor,
                after={"cutoff": cutoff.isoformat(), "count": count},
            )
        return count

    def purge_before(self, cutoff: datetime, *, actor: Actor) -> int:
        """Supprime les lignes antérieures à ``cutoff`` (durée de conservation, 3 ans, D15)."""
        from apps.core.audit import AuditAction, record

        with transaction.atomic():
            count = self.get_queryset().filter(at__lt=cutoff)._privileged_delete()
            record(
                AuditAction.AUDIT_PURGED,
                actor=actor,
                after={"cutoff": cutoff.isoformat(), "count": count},
            )
        return count

    def redact_network_for_user(self, user: AbstractBaseUser, *, actor: Actor) -> int:
        """Efface l'IP et le user-agent des actions d'un compte (anonymisation, §4.9).

        La ligne qui trace cette opération est écrite avant l'effacement : si le compte
        agit lui-même (anonymisation en libre-service), son propre contexte réseau est
        donc effacé avec le reste. ``count`` ne compte pas cette ligne.
        """
        from apps.core.audit import AuditAction, record

        with transaction.atomic():
            targets = (
                self.get_queryset()
                .filter(actor=user)
                .filter(Q(ip__isnull=False) | ~Q(user_agent=""))
            )
            count = targets.count()
            record(
                AuditAction.AUDIT_NETWORK_REDACTED, actor=actor, obj=user, after={"count": count}
            )
            # Requête réévaluée : inclut la ligne qui vient d'être écrite.
            targets._privileged_update(ip=None, user_agent="")
        return count


class AuditLog(models.Model):
    """Journal d'audit en ajout seul (RG-17, plan L1 §3.5 et §7).

    ``save()`` sur une ligne existante, ``delete()``, ``update()`` et ``delete()`` sur le
    queryset lèvent ``AppendOnlyError``. ``before`` et ``after`` ne contiennent que des
    champs en liste blanche (``AUDIT_FIELDS`` de chaque modèle, ``apps.core.audit``) :
    jamais de mot de passe, de secret, de jeton ni d'adresse e-mail en clair.
    """

    at = models.DateTimeField(_("date"), default=timezone.now, db_index=True)
    # Null = système ou visiteur anonyme. Après anonymisation, pointe vers le compte anonymisé.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("acteur"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="audit_entries",
    )
    actor_kind = models.CharField(_("type d'acteur"), max_length=8, choices=ActorKind.choices)
    # Commandes et tâches seulement (« cli:<utilisateur système> », « job:<type> ») ;
    # jamais l'adresse d'un utilisateur, qui survivrait à son anonymisation.
    actor_label = models.CharField(
        _("libellé de l'acteur"), max_length=LABEL_MAX_LENGTH, blank=True, default=""
    )
    action = models.CharField(_("action"), max_length=64)
    object_type = models.CharField(_("type d'objet"), max_length=64, blank=True, default="")
    object_id = models.CharField(_("identifiant de l'objet"), max_length=64, blank=True, default="")
    before = models.JSONField(_("avant"), null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(_("après"), null=True, blank=True, encoder=DjangoJSONEncoder)
    reason = models.TextField(_("motif"), blank=True, default="")
    request_id = models.CharField(
        _("identifiant de requête"), max_length=32, blank=True, default=""
    )
    # Contexte réseau : purgé après 6 mois (D15) et à l'anonymisation du compte.
    ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)
    user_agent = models.CharField(
        _("navigateur"), max_length=USER_AGENT_MAX_LENGTH, blank=True, default=""
    )

    objects = AuditLogManager()

    class Meta:
        verbose_name = _("entrée du journal d'audit")
        verbose_name_plural = _("journal d'audit")
        # L'index (edition, at) arrive avec la colonne edition (L1.5, §3.8).
        indexes = (
            models.Index(fields=["actor", "at"], name="core_audit_actor_at_idx"),
            models.Index(fields=["object_type", "object_id"], name="core_audit_object_idx"),
            models.Index(fields=["action", "at"], name="core_audit_action_at_idx"),
        )
        constraints = (
            _choices_check("actor_kind", ActorKind, "core_audit_actor_kind_valid"),
            # Même invariant qu'Actor : un utilisateur sans libellé ; une commande ou une
            # tâche avec libellé et sans compte.
            models.CheckConstraint(
                condition=Q(actor_kind=ActorKind.USER, actor_label="")
                | (
                    Q(actor_kind__in=[ActorKind.COMMAND, ActorKind.SYSTEM], actor__isnull=True)
                    & ~Q(actor_label="")
                ),
                name="core_audit_actor_consistent",
            ),
        )

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.action}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            _refuse("save() d'une ligne existante")
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        _refuse("delete()")


# --- File de tâches (plan L1 §3.5, §8.2) ------------------------------------------------


class JobStatus(models.TextChoices):
    PENDING = "pending", _("en attente")
    RUNNING = "running", _("en cours")
    SUCCEEDED = "succeeded", _("réussie")
    FAILED = "failed", _("en échec")
    CANCELLED = "cancelled", _("annulée")


class Job(TimeStampedModel):
    """Tâche asynchrone exécutée par ``manage.py run_jobs`` (cron) ou par la voie rapide.

    Livraison « au moins une fois » : chaque gestionnaire est idempotent (§8.2).
    """

    # Priorités usuelles (§3.5) : elles ne servent qu'à ordonner le cron.
    PRIORITY_URGENT: ClassVar[int] = 0  # e-mails de sécurité et de la voie rapide
    PRIORITY_DEFAULT: ClassVar[int] = 100
    PRIORITY_BULK: ClassVar[int] = 200  # envois de masse
    DEFAULT_MAX_ATTEMPTS: ClassVar[int] = 5

    kind = models.CharField(_("type"), max_length=64)
    # Identifiants et scalaires seulement, jamais de secret (contrôlé par enqueue()).
    payload = models.JSONField(_("données"), default=dict, blank=True)
    status = models.CharField(
        _("statut"), max_length=10, choices=JobStatus.choices, default=JobStatus.PENDING
    )
    priority = models.PositiveSmallIntegerField(_("priorité"), default=PRIORITY_DEFAULT)
    run_at = models.DateTimeField(_("à exécuter à partir de"), default=timezone.now)
    attempts = models.PositiveSmallIntegerField(_("tentatives"), default=0)
    max_attempts = models.PositiveSmallIntegerField(
        _("tentatives au plus"), default=DEFAULT_MAX_ATTEMPTS
    )
    locked_at = models.DateTimeField(_("réservée le"), null=True, blank=True)
    locked_by = models.CharField(_("réservée par"), max_length=64, blank=True, default="")
    finished_at = models.DateTimeField(_("terminée le"), null=True, blank=True)
    # Tronqué à 2 000 caractères, adresses masquées (apps.core.jobs.safe_error_text).
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")
    # Clé d'unicité nullable (plan L1 §3.1) : NULL = pas de déduplication. Construite par
    # le code, jamais à partir d'une adresse e-mail.
    dedup_key = models.CharField(
        _("clé de déduplication"), max_length=128, null=True, blank=True, unique=True
    )

    class Meta:
        verbose_name = _("tâche")
        verbose_name_plural = _("tâches")
        indexes = (
            models.Index(fields=["status", "priority", "run_at"], name="core_job_queue_idx"),
        )
        constraints = (
            _choices_check("status", JobStatus, "core_job_status_valid"),
            models.CheckConstraint(
                condition=Q(max_attempts__gte=1), name="core_job_max_attempts_positive"
            ),
            models.CheckConstraint(condition=~Q(dedup_key=""), name="core_job_dedup_key_not_blank"),
        )

    def __str__(self) -> str:
        return f"{self.kind} #{self.pk} ({self.status})"


# --- Battement de cœur des commandes cron (plan L1 §3.5, §8.4) ----------------------------


class HeartbeatStatus(models.TextChoices):
    RUNNING = "running", _("en cours")
    SUCCEEDED = "succeeded", _("réussie")
    FAILED = "failed", _("en échec")


class CronHeartbeat(TimeStampedModel):
    """Dernier passage d'une commande d'exploitation (``LockedCommand``).

    Trace des commandes cron, qui ne sont pas auditées à chaque passage (arbitrage L1.2) ;
    alimente le champ ``jobs`` de ``/health`` (``last_success_at`` de ``run_jobs``).
    """

    name = models.CharField(_("commande"), max_length=64, unique=True)
    last_started_at = models.DateTimeField(_("dernier démarrage"), null=True, blank=True)
    last_finished_at = models.DateTimeField(_("dernière fin"), null=True, blank=True)
    last_success_at = models.DateTimeField(_("dernier succès"), null=True, blank=True)
    last_status = models.CharField(
        _("dernier statut"), max_length=10, choices=HeartbeatStatus.choices, blank=True, default=""
    )
    last_duration_ms = models.PositiveIntegerField(_("dernière durée (ms)"), null=True, blank=True)
    processed_count = models.PositiveIntegerField(_("éléments traités"), default=0)
    last_error = models.TextField(_("dernière erreur"), blank=True, default="")
    # Résumé du dernier passage (par exemple les compteurs de « cleanup »), sans donnée
    # personnelle : des nombres par règle.
    summary = models.JSONField(_("résumé"), null=True, blank=True, encoder=DjangoJSONEncoder)

    class Meta:
        verbose_name = _("battement de cœur")
        verbose_name_plural = _("battements de cœur")
        constraints = (
            models.CheckConstraint(
                condition=Q(last_status="") | Q(last_status__in=HeartbeatStatus.values),
                name="core_heartbeat_status_valid",
            ),
        )

    def __str__(self) -> str:
        return f"{self.name} ({self.last_status or '-'})"
