from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser
from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.accounts.managers import UserManager
from apps.accounts.roles import InvitableRole, OcFunction, Role
from apps.accounts.validators import validate_country, validate_orcid
from apps.core.models import AppendOnlyModel, TimeStampedModel


class User(AbstractBaseUser, TimeStampedModel):
    """Compte unique pour tous les rôles (étude §4 M2 et §8.2, table « user »).

    Le profil (nom, institution, ORCID...) est dans ``Profile`` ; la vérification
    des adresses dans les tables d'allauth (``EmailAddress``) ; les rôles par
    édition dans ``UserRole`` (L1.5) ; la 2FA dans ``mfa_authenticator`` (L1.6).

    Pas de PermissionsMixin : son champ is_superuser serait un rôle global
    implicite, contraire à la règle des rôles rattachés à une édition.
    """

    email = models.EmailField(_("adresse e-mail"), unique=True)
    is_active = models.BooleanField(_("actif"), default=True)
    locale = models.CharField(
        _("langue"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE
    )
    # Anonymisation (M2, RG-18, L1.8) : le compte ne peut plus se connecter.
    anonymized_at = models.DateTimeField(_("anonymisé le"), null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("utilisateur")
        verbose_name_plural = _("utilisateurs")

    def __str__(self) -> str:
        return self.email

    def clean(self) -> None:
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)


class ProfileTitle(models.TextChoices):
    """Titre affiché (M2 ; remplace la « civilité » de l'étude §8.2). Liste à valider."""

    NONE = "", _("aucun")
    DR = "dr", _("Dr")
    PR = "pr", _("Pr")
    MR = "mr", _("M.")
    MS = "ms", _("Mme")


BIO_MAX_LENGTH = 2000


class Profile(TimeStampedModel):
    """Profil d'un compte (plan L1 §3.3), créé à la première écriture.

    Son absence signifie « profil incomplet ». Données personnelles : jamais
    journalisées dans ``before``/``after`` de l'audit (seule la liste des champs
    modifiés l'est, §7.3).
    """

    user = models.OneToOneField(
        User,
        verbose_name=_("utilisateur"),
        on_delete=models.RESTRICT,
        primary_key=True,
        related_name="profile",
    )
    title = models.CharField(
        _("titre"), max_length=8, choices=ProfileTitle.choices, blank=True, default=""
    )
    first_name = models.CharField(_("prénom"), max_length=150, blank=True, default="")
    last_name = models.CharField(_("nom"), max_length=150, blank=True, default="")
    institution = models.CharField(_("institution"), max_length=255, blank=True, default="")
    department = models.CharField(_("département"), max_length=255, blank=True, default="")
    # Code ISO 3166-1 alpha-2, contrôlé par un validateur (pas de « choices », §9.5).
    country = models.CharField(
        _("pays"), max_length=2, blank=True, default="", validators=[validate_country]
    )
    orcid = models.CharField(
        _("ORCID"),
        max_length=19,
        blank=True,
        default="",
        db_index=True,
        validators=[validate_orcid],
    )
    bio = models.TextField(
        _("biographie"),
        blank=True,
        default="",
        validators=[MaxLengthValidator(BIO_MAX_LENGTH)],
    )

    # Champs exigés pour un profil complet (prérequis de la soumission en L3).
    REQUIRED_FIELDS: ClassVar[tuple[str, ...]] = (
        "first_name",
        "last_name",
        "institution",
        "country",
    )

    class Meta:
        verbose_name = _("profil")
        verbose_name_plural = _("profils")
        indexes = (models.Index(fields=["last_name", "first_name"], name="accounts_profile_name"),)

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or str(self.user_id)

    @property
    def is_complete(self) -> bool:
        return all(getattr(self, name).strip() for name in self.REQUIRED_FIELDS)


class ConsentKind(models.TextChoices):
    # Prise de connaissance de la notice d'information (ce n'est pas un consentement, D15).
    PRIVACY_NOTICE = "privacy_notice", _("notice d'information")
    # Apparition dans l'annuaire public des comités (affiché en L2).
    DIRECTORY_LISTING = "directory_listing", _("annuaire public")


class ConsentSource(models.TextChoices):
    FIRST_LOGIN = "first_login", _("première connexion")
    ACCOUNT = "account", _("espace compte")
    COMMAND = "command", _("commande")


class Consent(AppendOnlyModel):
    """Consentements horodatés et versionnés (plan L1 §3.3 et §4.8), en ajout seul.

    Un retrait est une nouvelle ligne à ``granted=False`` ; l'état courant est la
    dernière ligne de chaque (``user``, ``kind``). Comme le journal d'audit, la
    table refuse modification et suppression, sauf par deux méthodes nommées et
    auditées qui effacent l'IP (D15 : 6 mois ; anonymisation du compte).
    """

    user = models.ForeignKey(
        User, verbose_name=_("utilisateur"), on_delete=models.RESTRICT, related_name="consents"
    )
    kind = models.CharField(_("type"), max_length=32, choices=ConsentKind.choices)
    granted = models.BooleanField(_("accordé"))
    text_version = models.CharField(_("version du texte"), max_length=32)
    recorded_at = models.DateTimeField(_("enregistré le"))
    source = models.CharField(_("origine"), max_length=16, choices=ConsentSource.choices)
    ip = models.GenericIPAddressField(_("adresse IP"), null=True, blank=True)

    class Meta:
        verbose_name = _("consentement")
        verbose_name_plural = _("consentements")
        indexes = (
            models.Index(fields=["user", "kind", "recorded_at"], name="accounts_consent_state"),
        )

    def __str__(self) -> str:
        return f"{self.kind}={self.granted} ({self.text_version})"

    @classmethod
    def purge_network_before(cls, date: datetime, *, actor: Any) -> int:
        """Efface l'IP des consentements antérieurs à ``date`` (D15 : 6 mois)."""
        from apps.core.audit import record

        count = cls.objects.filter(recorded_at__lt=date, ip__isnull=False)._unchecked_update(
            ip=None
        )
        record("consent.network_purged", actor=actor, after={"before": date, "count": count})
        return count

    @classmethod
    def redact_network_for_user(cls, user: User, *, actor: Any) -> int:
        """Efface l'IP des consentements d'un compte (anonymisation, plan §4.9)."""
        from apps.core.audit import record

        count = cls.objects.filter(user=user, ip__isnull=False)._unchecked_update(ip=None)
        record("consent.network_redacted", actor=actor, obj=user, after={"count": count})
        return count


# --- Rôles par édition et invitations (plan L1 §3.3, D6) --------------------------------


class UserRoleStatus(models.TextChoices):
    ACTIVE = "active", _("actif")
    REVOKED = "revoked", _("révoqué")


class RoleSource(models.TextChoices):
    INVITATION = "invitation", _("invitation")
    COMMAND = "command", _("commande")
    SYSTEM = "system", _("système")


# CHECK : fonction CO renseignée si et seulement si le rôle est OC_MEMBER (D8).
_OC_FUNCTION_CHECK = models.Q(role=Role.OC_MEMBER, oc_function__gt="") | (
    ~models.Q(role=Role.OC_MEMBER) & models.Q(oc_function="")
)


class UserRole(TimeStampedModel):
    """Rôle d'un compte dans une édition (règle n° 5). Seul ``active`` donne des droits.

    Une ligne n'existe qu'après attribution ou acceptation : un invité ne détient aucun
    droit, par construction (D6). Une réattribution après révocation réactive la même
    ligne ; l'historique est dans le journal d'audit.
    """

    user = models.ForeignKey(
        User, verbose_name=_("utilisateur"), on_delete=models.RESTRICT, related_name="roles"
    )
    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="user_roles",
    )
    role = models.CharField(_("rôle"), max_length=16, choices=Role.choices)
    # NOT NULL, "" par défaut : une colonne NULL rendrait l'unicité inopérante (§3.1).
    oc_function = models.CharField(
        _("fonction au CO"), max_length=32, choices=OcFunction.choices, blank=True, default=""
    )
    status = models.CharField(
        _("statut"), max_length=8, choices=UserRoleStatus.choices, default=UserRoleStatus.ACTIVE
    )
    source = models.CharField(_("origine"), max_length=16, choices=RoleSource.choices)
    granted_at = models.DateTimeField(_("attribué le"))
    granted_by = models.ForeignKey(
        User,
        verbose_name=_("attribué par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    revoked_at = models.DateTimeField(_("révoqué le"), null=True, blank=True)
    revoked_by = models.ForeignKey(
        User,
        verbose_name=_("révoqué par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    revoke_reason = models.TextField(_("motif de révocation"), blank=True, default="")
    invitation = models.ForeignKey(
        "accounts.RoleInvitation",
        verbose_name=_("invitation"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "user",
        "edition",
        "role",
        "oc_function",
        "status",
        "source",
    )

    class Meta:
        verbose_name = _("rôle")
        verbose_name_plural = _("rôles")
        constraints = (
            models.UniqueConstraint(
                fields=["user", "edition", "role", "oc_function"], name="accounts_userrole_unique"
            ),
            models.CheckConstraint(condition=_OC_FUNCTION_CHECK, name="accounts_userrole_oc_fn"),
        )
        indexes = (
            models.Index(fields=["edition", "role", "status"], name="accounts_userrole_edition"),
            models.Index(fields=["user", "status"], name="accounts_userrole_user"),
        )

    def __str__(self) -> str:
        return f"{self.role}@{self.edition_id}"


class InvitationStatus(models.TextChoices):
    PENDING = "pending", _("en attente")
    ACCEPTED = "accepted", _("acceptée")
    DECLINED = "declined", _("refusée")
    CANCELLED = "cancelled", _("annulée")
    EXPIRED = "expired", _("expirée")


MESSAGE_MAX_LENGTH = 1000


class RoleInvitation(TimeStampedModel):
    """Invitation à un rôle, adressée à un e-mail, avec ou sans compte (D6, §5.7).

    Le jeton n'est jamais stocké en clair (``token_hash``). ``pending_key`` (empreinte
    SHA-256, longueur fixe) n'est renseignée que tant que l'invitation est en attente :
    la base garantit ainsi une seule invitation en attente par (édition, adresse, rôle,
    fonction), sans unicité conditionnelle (§3.1). Statut modifié par le service seulement.
    """

    edition = models.ForeignKey(
        "conferences.Edition",
        verbose_name=_("édition"),
        on_delete=models.RESTRICT,
        related_name="invitations",
    )
    email = models.EmailField(_("adresse invitée"))
    role = models.CharField(_("rôle"), max_length=16, choices=InvitableRole.choices)
    oc_function = models.CharField(
        _("fonction au CO"), max_length=32, choices=OcFunction.choices, blank=True, default=""
    )
    token_hash = models.CharField(_("empreinte du jeton"), max_length=64, unique=True)
    status = models.CharField(
        _("statut"),
        max_length=12,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )
    pending_key = models.CharField(
        _("clé d'unicité en attente"), max_length=64, null=True, blank=True, unique=True
    )
    invited_by = models.ForeignKey(
        User,
        verbose_name=_("invité par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )
    expires_at = models.DateTimeField(_("expire le"))
    locale = models.CharField(_("langue"), max_length=8)
    message = models.TextField(_("message"), blank=True, default="")
    send_count = models.PositiveSmallIntegerField(_("envois"), default=1)
    last_sent_at = models.DateTimeField(_("dernier envoi"))
    responded_at = models.DateTimeField(_("répondu le"), null=True, blank=True)
    accepted_by = models.ForeignKey(
        User,
        verbose_name=_("acceptée par"),
        null=True,
        blank=True,
        on_delete=models.RESTRICT,
        related_name="+",
    )

    # Jamais l'adresse en clair : seulement sa forme masquée (plan §7.2).
    AUDIT_FIELDS: ClassVar[tuple[str, ...]] = (
        "edition",
        "email_masked",
        "role",
        "oc_function",
        "status",
        "expires_at",
        "send_count",
    )

    class Meta:
        verbose_name = _("invitation")
        verbose_name_plural = _("invitations")
        constraints = (
            models.CheckConstraint(condition=_OC_FUNCTION_CHECK, name="accounts_invitation_oc_fn"),
        )
        indexes = (
            models.Index(fields=["edition", "status"], name="accounts_invitation_edition"),
            models.Index(fields=["email", "status"], name="accounts_invitation_email"),
            models.Index(fields=["invited_by", "created_at"], name="accounts_invitation_quota"),
        )

    def __str__(self) -> str:
        return f"{self.role}@{self.edition_id} ({self.status})"

    @property
    def email_masked(self) -> str:
        from apps.core.audit import mask_email

        return mask_email(self.email)
