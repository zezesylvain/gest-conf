"""Catalogue des codes d'erreur de l'API et erreurs métier (plan L1 §9.1).

Deux éléments, indépendants de HTTP :

- ``ErrorCode`` : liste fermée des codes que l'API peut renvoyer dans le champ
  ``code`` du format d'erreur ``{code, message, fields}``. Le client Angular
  traduit chaque code ; le schéma OpenAPI l'expose sous le nom ``ErrorCode``.
  Un code n'y entre que lorsqu'un chemin de code peut l'émettre : les codes des
  étapes suivantes (rôles, invitations, 2FA...) seront ajoutés avec elles.
- ``DomainError`` et ses sous-classes : levées par les services métier, qui ne
  connaissent pas HTTP. Le gestionnaire d'exceptions de l'API
  (``apps.core.exceptions``) les traduit en réponses HTTP.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import ClassVar

from django.db import models
from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

type Message = str | Promise


class ErrorCode(models.TextChoices):
    """Codes d'erreur stables de l'API (valeurs en anglais, jamais renommées)."""

    # Gestionnaire d'exceptions et vues d'erreur de Django (lot L0).
    VALIDATION_ERROR = "validation_error"
    BAD_REQUEST = "bad_request"
    NOT_AUTHENTICATED = "not_authenticated"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"
    THROTTLED = "throttled"
    SERVER_ERROR = "server_error"
    # Codes par défaut des exceptions DRF que l'API peut produire
    # (rest_framework/exceptions.py) : corps JSON illisible, méthode non
    # autorisée, en-tête Accept non satisfiable, type de contenu refusé.
    PARSE_ERROR = "parse_error"
    METHOD_NOT_ALLOWED = "method_not_allowed"
    NOT_ACCEPTABLE = "not_acceptable"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    # Échec du contrôle CSRF, sur les trois chemins (plan L1 §4.6).
    CSRF_FAILED = "csrf_failed"
    # Règle métier : objet encore utilisé (par exemple une grille déjà employée).
    IN_USE = "in_use"
    # Réauthentification récente exigée (RecentAuthRequired, plan L1 §4.5).
    REAUTHENTICATION_REQUIRED = "reauthentication_required"
    # 2FA imposée aux rôles de gestion (MfaVerified, plan L1 §4.4) : pas encore activée,
    # ou pas encore validée dans la session.
    MFA_ENROLLMENT_REQUIRED = "mfa_enrollment_required"
    MFA_REQUIRED = "mfa_required"
    # Rôles et invitations (plan L1 §5.5, §5.7, RG-20).
    LAST_ADMIN = "last_admin"
    INVITATION_EXPIRED = "invitation_expired"
    INVITATION_NOT_PENDING = "invitation_not_pending"
    INVITATION_EMAIL_MISMATCH = "invitation_email_mismatch"
    INVITATION_EMAIL_UNVERIFIED = "invitation_email_unverified"
    INVITATION_LINK_INVALID = "invitation_link_invalid"
    INVITATION_SELF_ACCEPT = "invitation_self_accept"
    INVITATION_RESEND_LIMIT = "invitation_resend_limit"
    EMAIL_ADDRESS_LIMIT = "email_address_limit"
    # Édition (plan L1 §6.3) : écriture sur une édition archivée, transition illégale,
    # préconditions de publication non remplies.
    EDITION_ARCHIVED = "edition_archived"
    INVALID_TRANSITION = "invalid_transition"
    EDITION_INCOMPLETE = "edition_incomplete"
    # Données personnelles (plan L1 §4.9) : anonymisation refusée tant que des
    # responsabilités (rôles de gestion actifs, dernier ADMIN) n'ont pas été transmises.
    ACCOUNT_HAS_ACTIVE_DUTIES = "account_has_active_duties"
    # Soumissions (plan L3) : soumission incomplète (RG-01), appel clos sans dérogation
    # (RG-02), réglage de l'édition gelé par l'existence de soumissions (RG-19).
    SUBMISSION_INCOMPLETE = "submission_incomplete"
    CALL_CLOSED = "call_closed"
    SETTING_FROZEN = "setting_frozen"
    # Écriture concurrente (If-Match périmé, plan L3 §4) : relire avant de réécrire.
    STALE_REVISION = "stale_revision"
    # Soumission dans un état qui n'admet plus de modification par l'auteur ; profil
    # incomplet (prérequis de la soumission, plan L1 §3.3).
    SUBMISSION_LOCKED = "submission_locked"
    PROFILE_INCOMPLETE = "profile_incomplete"
    # Évaluation (plan L4) : grille utilisée par une évaluation (RG-05 : on la duplique).
    GRID_LOCKED = "grid_locked"
    # Affectations (plan L4, H6, H8, H10) : conflit d'intérêts, charge maximale atteinte,
    # relecteurs requis non affectés, évaluation non ouverte (ou close) pour la soumission.
    CONFLICT_OF_INTEREST = "conflict_of_interest"
    REVIEWER_OVERLOADED = "reviewer_overloaded"
    REVIEWERS_MISSING = "reviewers_missing"
    REVIEW_NOT_OPEN = "review_not_open"
    # Discussion (RG-08) : non ouverte, ou évaluation du relecteur pas encore envoyée.
    DISCUSSION_CLOSED = "discussion_closed"
    # Échéance passée (version finale après la date clé « camera_ready », H18).
    DEADLINE_PASSED = "deadline_passed"


class DomainError(Exception):
    """Erreur métier levée par un service.

    Porte un code du catalogue, un message traduisible (évalué au moment de la
    réponse, donc dans la langue de la requête) et, facultativement, des
    erreurs par champ ``{"champ": ["message", ...]}``.
    """

    default_code: ClassVar[ErrorCode | None] = None
    default_message: ClassVar[Message] = _("Opération refusée.")

    def __init__(
        self,
        message: Message | None = None,
        *,
        code: ErrorCode | str | None = None,
        fields: Mapping[str, Sequence[Message]] | None = None,
    ) -> None:
        resolved = code if code is not None else self.default_code
        if resolved is None:
            raise TypeError(f"{type(self).__name__} exige un code du catalogue ErrorCode.")
        # ValueError si le code n'appartient pas au catalogue : l'erreur est
        # détectée là où elle est levée, et non par le client.
        self.code = ErrorCode(resolved)
        self.message: Message = message if message is not None else self.default_message
        self.fields: dict[str, list[Message]] = {
            name: list(messages) for name, messages in (fields or {}).items()
        }
        super().__init__(self.code.value)


class RuleViolation(DomainError):
    """Une règle de gestion interdit l'opération dans l'état actuel (HTTP 409).

    Le code est obligatoire : un conflit sans code précis n'est pas exploitable
    par l'interface.
    """

    default_message = _("Opération impossible dans l'état actuel.")


class NotAllowed(DomainError):
    """L'acteur n'a pas le droit d'effectuer l'opération (HTTP 403)."""

    default_code = ErrorCode.PERMISSION_DENIED
    default_message = _("Action non autorisée.")


class Invalid(DomainError):
    """Les données fournies au service sont invalides (HTTP 400)."""

    default_code = ErrorCode.VALIDATION_ERROR
    default_message = _("Données invalides.")


class StaleRevision(DomainError):
    """La ressource a changé depuis sa lecture (``If-Match`` périmé, HTTP 412)."""

    default_code = ErrorCode.STALE_REVISION
    default_message = _("Modifié entre-temps (autre onglet ?) : rechargez avant d'enregistrer.")


class QuotaExceeded(DomainError):
    """Quota métier dépassé (HTTP 429, code ``throttled``, en-tête ``Retry-After``).

    Complète la limitation de débit de DRF, qui compte des requêtes, quand le
    service doit compter autre chose (par exemple des adresses invitées).
    """

    default_code = ErrorCode.THROTTLED
    default_message = _("Quota atteint.")

    def __init__(
        self,
        message: Message | None = None,
        *,
        retry_after: float,
        fields: Mapping[str, Sequence[Message]] | None = None,
    ) -> None:
        if retry_after <= 0:
            raise ValueError("retry_after doit être strictement positif (en secondes).")
        super().__init__(message, fields=fields)
        self.retry_after = retry_after
