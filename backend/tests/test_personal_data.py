"""Données personnelles (plan L1 §4.9, §12.1 ; RG-18, D15).

- registre complet (introspection) ;
- export sans secret ;
- anonymisation : refus tant que des responsabilités subsistent, puis **balayage** de
  toutes les colonnes texte de tous les modèles (tables tierces comprises) et des sessions ;
- API, commandes, durées de conservation, contrôles d'intégrité.
"""

from __future__ import annotations

import json

import pytest
from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from django.apps import apps
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.db import models
from django.utils import timezone

from apps.accounts.models import (
    Consent,
    ConsentKind,
    ConsentSource,
    InvitationStatus,
    Profile,
    RoleInvitation,
    RoleSource,
    User,
    UserRole,
    UserRoleStatus,
)
from apps.accounts.roles import Role
from apps.accounts.services.personal_data import (
    anonymize_user,
    export_user_data,
    redact_old_invitations,
)
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, enable_totp, make_member
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import RuleViolation
from apps.core.models import AuditLog
from apps.core.personal_data import covered_models, exemptions

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")
FIRST_NAME = "Zéphyrine"
LAST_NAME = "Kpangbalo"
EMAIL = "zephyrine.kpangbalo@univ-test.ci"
SECOND_EMAIL = "zk.perso@exemple-test.org"


# --- Registre (introspection) ----------------------------------------------------------


def _models_with_personal_data() -> set[str]:
    user_model = apps.get_model(settings.AUTH_USER_MODEL)
    labels = set()
    for model in apps.get_models():
        for field in model._meta.get_fields():
            concrete = getattr(field, "concrete", False)
            points_to_user = getattr(field, "related_model", None) is user_model
            if concrete and (points_to_user or isinstance(field, models.EmailField)):
                labels.add(model._meta.label)
    return labels


def test_personal_data_registry_covers_all_user_fks():
    """Plan §4.9 : tout modèle lié à un compte (clé vers User ou EmailField) est déclaré
    au registre ou exempté avec une justification."""
    missing = _models_with_personal_data() - covered_models() - set(exemptions())
    assert missing == set()


# --- Export -------------------------------------------------------------------------------


def test_rg18_export_contains_every_section_and_no_secret():
    user = VerifiedUserFactory(email=EMAIL)
    Profile.objects.create(user=user, first_name=FIRST_NAME, last_name=LAST_NAME)
    enable_totp(user)
    data = export_user_data(user, actor=COMMAND)
    assert data["format"] == "gestconf-export-v1"
    expected = {"account", "profile", "email_addresses", "mfa", "roles", "invitations"}
    assert expected | {"consents", "emails", "audit"} <= set(data)
    assert data["profile"]["last_name"] == LAST_NAME
    assert data["mfa"][0]["type"] == "totp"
    text = json.dumps(data)
    assert "secret" not in text and "password" not in text
    assert AuditLog.objects.filter(action="account.exported").exists()


# --- Anonymisation : refus -------------------------------------------------------------


def test_rg18_anonymization_refused_with_active_duties():
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    with pytest.raises(RuleViolation) as error:
        anonymize_user(chair, actor=COMMAND, reason="Demande écrite")
    assert error.value.code == "account_has_active_duties"
    assert User.objects.get(pk=chair.pk).anonymized_at is None


def test_rg18_last_admin_of_archived_edition_must_hand_over():
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    admin = make_member(edition, Role.ADMIN)
    with pytest.raises(RuleViolation):
        anonymize_user(admin, actor=COMMAND, reason="x")


def test_author_and_role_in_archived_edition_do_not_block():
    archived = EditionFactory(status=EditionStatus.ARCHIVED)
    user = make_member(archived, Role.SC_MEMBER)
    UserRole.objects.create(
        user=user,
        edition=EditionFactory(),
        role=Role.AUTHOR,
        source=RoleSource.SYSTEM,
        granted_at=timezone.now(),
    )
    anonymize_user(user, actor=COMMAND, reason="Demande")
    assert not UserRole.objects.filter(user=user, status=UserRoleStatus.ACTIVE).exists()


# --- Anonymisation : balayage ----------------------------------------------------------


def _seed_personal_data(user: User, edition) -> None:
    """Le nom et l'adresse injectés partout où un texte libre peut les recevoir."""
    Profile.objects.create(
        user=user,
        first_name=FIRST_NAME,
        last_name=LAST_NAME,
        institution="Université test",
        bio=f"Je suis {FIRST_NAME} {LAST_NAME}, joignable à {EMAIL}.",
    )
    EmailAddress.objects.create(user=user, email=SECOND_EMAIL, verified=True, primary=False)
    enable_totp(user)
    Consent.objects.create(
        user=user,
        kind=ConsentKind.DIRECTORY_LISTING,
        granted=True,
        text_version="v0",
        recorded_at=timezone.now(),
        source=ConsentSource.ACCOUNT,
        ip="203.0.113.7",
    )
    inviter = VerifiedUserFactory()
    # Invitation reçue à son adresse secondaire (en attente) et invitation qu'il a envoyée.
    RoleInvitation.objects.create(
        edition=edition,
        email=SECOND_EMAIL,
        role=Role.SC_MEMBER,
        token_hash="a" * 64,
        pending_key="b" * 64,
        invited_by=inviter,
        expires_at=timezone.now() + timezone.timedelta(days=7),
        last_sent_at=timezone.now(),
        message=f"Bonjour {FIRST_NAME},",
    )
    RoleInvitation.objects.create(
        edition=edition,
        email="collegue@exemple-test.org",
        role=Role.SC_MEMBER,
        status=InvitationStatus.DECLINED,
        token_hash="c" * 64,
        invited_by=user,
        expires_at=timezone.now(),
        last_sent_at=timezone.now(),
        message=f"Cordialement, {FIRST_NAME} {LAST_NAME} ({EMAIL})",
    )
    OutboxEmail.objects.create(
        to_email=EMAIL,
        to_user=user,
        template_code="account/email/password_changed",
        locale="fr",
        subject=f"Bonjour {FIRST_NAME} {LAST_NAME}",
        body_text=f"Bonjour {FIRST_NAME} {LAST_NAME}",
        status=OutboxStatus.SENT,
        scheduled_at=timezone.now(),
    )
    # E-mail envoyé à un tiers qui cite son nom (invitation qu'il a envoyée).
    OutboxEmail.objects.create(
        to_email="collegue@exemple-test.org",
        template_code="role/email/invitation",
        locale="fr",
        subject="Invitation",
        body_text=f"{FIRST_NAME} {LAST_NAME} vous invite.",
        status=OutboxStatus.SENT,
        scheduled_at=timezone.now(),
    )
    record("profile.updated", actor=Actor(kind="user", user=user, ip="203.0.113.7"), obj=user)


def _text_values(model) -> list[str]:
    fields = [
        field.attname
        for field in model._meta.concrete_fields
        if isinstance(field, models.CharField | models.TextField | models.JSONField)
    ]
    if not fields:
        return []
    return [str(value) for row in model.objects.values_list(*fields) for value in row]


def test_rg18_anonymization_sweeps_every_text_column():
    """Plan §4.9, test de balayage : après l'anonymisation, aucune colonne texte d'aucun
    modèle (tables tierces comprises) ni aucune session ne contient l'adresse ou le nom."""
    edition = EditionFactory()
    user = VerifiedUserFactory(email=EMAIL)
    _seed_personal_data(user, edition)
    client = client_for(user)
    assert Session.objects.exists()

    anonymize_user(user, actor=COMMAND, reason="Demande écrite")

    needles = [EMAIL.lower(), SECOND_EMAIL.lower(), FIRST_NAME.lower(), LAST_NAME.lower()]
    leaks = []
    for model in apps.get_models():
        for value in _text_values(model):
            lowered = value.lower()
            leaks += [(model._meta.label, needle) for needle in needles if needle in lowered]
    for session in Session.objects.all():
        decoded = json.dumps(session.get_decoded()).lower()
        leaks += [("session", needle) for needle in needles if needle in decoded]
    assert leaks == []
    # Effets attendus.
    user.refresh_from_db()
    assert user.email == f"anonymized-{user.pk}@anonymized.invalid"
    assert not user.is_active and not user.has_usable_password()
    assert not Authenticator.objects.filter(user=user).exists()
    assert not EmailAddress.objects.filter(user=user).exists()
    assert Consent.objects.get(user=user).ip is None
    # Invitation envoyée : message (signature) vidé ; invitation reçue : adresse anonymisée.
    assert RoleInvitation.objects.get(token_hash="c" * 64).message == ""
    assert RoleInvitation.objects.get(token_hash="a" * 64).email == user.email
    assert client.get("/v1/me").status_code == 401
    entry = AuditLog.objects.get(action="account.anonymized")
    assert entry.reason == "Demande écrite"


def test_rg18_pending_invitation_to_anonymized_address_is_cancelled():
    edition = EditionFactory()
    user = VerifiedUserFactory(email=EMAIL)
    _seed_personal_data(user, edition)
    anonymize_user(user, actor=COMMAND, reason="x")
    received = RoleInvitation.objects.get(token_hash="a" * 64)
    assert received.status == InvitationStatus.CANCELLED
    assert received.pending_key is None


def test_anonymization_is_idempotent():
    user = VerifiedUserFactory()
    anonymize_user(user, actor=COMMAND, reason="x")
    anonymize_user(user, actor=COMMAND, reason="x")
    assert AuditLog.objects.filter(action="account.anonymized").count() == 1


# --- API ----------------------------------------------------------------------------------


def test_data_export_endpoint_requires_recent_authentication():
    user = VerifiedUserFactory()
    stale = client_for(user, recent_auth=False, mfa=False)
    assert stale.get("/v1/me/data-export").json()["code"] == "reauthentication_required"
    response = client_for(user, mfa=False).get("/v1/me/data-export")
    assert response.status_code == 200
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Cache-Control"] == "no-store"
    assert response.json()["account"]["email"] == user.email


def test_anonymization_endpoint_requires_confirmation_and_logs_out():
    user = VerifiedUserFactory(email=EMAIL)
    client = client_for(user, mfa=False)
    wrong = client.post("/v1/me/anonymization", {"confirmation": "autre@exemple.org"})
    assert wrong.status_code == 400
    assert "confirmation" in wrong.json()["fields"]
    response = client.post("/v1/me/anonymization", {"confirmation": EMAIL.upper()})
    assert response.status_code == 204
    assert User.objects.get(pk=user.pk).anonymized_at is not None
    assert client.get("/v1/me").status_code == 401


def test_anonymization_endpoint_refuses_active_duties():
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    response = client_for(chair).post("/v1/me/anonymization", {"confirmation": chair.email})
    assert response.status_code == 409
    assert response.json()["code"] == "account_has_active_duties"


# --- Commandes ----------------------------------------------------------------------------


def test_export_and_anonymize_commands(tmp_path):
    user = VerifiedUserFactory(email=EMAIL)
    output = tmp_path / "export.json"
    call_command("export_user_data", "--email", EMAIL, "--output", str(output))
    assert json.loads(output.read_text())["account"]["email"] == EMAIL
    assert output.stat().st_mode & 0o777 == 0o600
    call_command("anonymize_user", "--email", EMAIL, "--reason", "Courrier du 5 octobre")
    assert User.objects.get(pk=user.pk).anonymized_at is not None
    with pytest.raises(CommandError):
        call_command(
            "reactivate_user",
            "--email",
            f"anonymized-{user.pk}@anonymized.invalid",
            "--reason",
            "x",
        )


def test_reactivate_user_command():
    user = VerifiedUserFactory(is_active=False)
    call_command("reactivate_user", "--email", user.email, "--reason", "Erreur de désactivation")
    assert User.objects.get(pk=user.pk).is_active
    assert AuditLog.objects.get(action="account.reactivated").reason == "Erreur de désactivation"


# --- Conservation (D15) et intégrité --------------------------------------------------------


def test_old_declined_invitations_are_redacted_when_enforced():
    edition = EditionFactory()
    invitation = RoleInvitation.objects.create(
        edition=edition,
        email="ancien@exemple-test.org",
        role=Role.SC_MEMBER,
        status=InvitationStatus.DECLINED,
        token_hash="d" * 64,
        expires_at=timezone.now(),
        last_sent_at=timezone.now(),
        message="Message ancien",
    )
    RoleInvitation.objects.filter(pk=invitation.pk).update(
        updated_at=timezone.now() - timezone.timedelta(days=400)
    )
    assert redact_old_invitations(True, timezone.now()) == 1
    assert redact_old_invitations(False, timezone.now()) == 1
    invitation.refresh_from_db()
    assert invitation.email.endswith("@anonymized.invalid") and invitation.message == ""
    assert redact_old_invitations(True, timezone.now()) == 0


def test_cleanup_reports_new_retention_tasks_in_simulation(settings):
    settings.GESTCONF_RETENTION_ENFORCED = False
    call_command("cleanup", verbosity=0)
    tasks = AuditLog.objects.get(action="retention.applied").after["tasks"]
    for name in (
        "core.audit_network",
        "core.audit_rows",
        "accounts.consent_network",
        "accounts.invitation_redact",
        "communications.old_metadata",
    ):
        assert tasks[name]["dry_run"] is True


def test_check_integrity_reports_duplicates_and_alerts(settings, mailoutbox):
    settings.ADMINS = [("Opérateur", "ops@exemple-test.org")]
    first = VerifiedUserFactory()
    second = VerifiedUserFactory()
    EmailAddress.objects.create(user=second, email=first.email.upper(), verified=True)
    call_command("check_integrity", verbosity=0)
    entry = AuditLog.objects.get(action="integrity.checked")
    assert entry.after["problems"] == {"accounts.duplicate_verified_emails": 1}
    assert len(mailoutbox) == 1
    assert first.email not in mailoutbox[0].body


def test_check_integrity_clean_database_sends_nothing(settings, mailoutbox):
    settings.ADMINS = [("Opérateur", "ops@exemple-test.org")]
    VerifiedUserFactory()
    call_command("check_integrity", verbosity=0)
    assert AuditLog.objects.get(action="integrity.checked").after["problems"] == {}
    assert mailoutbox == []
