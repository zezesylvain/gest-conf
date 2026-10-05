"""Journal d'audit (RG-17, plan L1 §7) : service, garde-fous et immuabilité."""

from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.communications.models import OutboxEmail
from apps.core.actor import Actor, ActorKind
from apps.core.audit import AuditDataError, mask_email, record, snapshot
from apps.core.models import AppendOnlyError, AuditLog

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")


def user_actor(user, **extra):
    return Actor(kind=ActorKind.USER, user=user, ip="203.0.113.7", user_agent="UA", **extra)


def test_rg17_record_stores_actor_object_and_context():
    user = UserFactory()
    entry = record(
        "account.updated",
        actor=user_actor(user, request_id="a" * 32),
        obj=user,
        before={"locale": "fr"},
        after={"locale": "en"},
        reason="demande",
    )
    entry.refresh_from_db()
    assert entry.actor == user
    assert entry.actor_kind == ActorKind.USER
    assert entry.actor_label == ""
    assert (entry.object_type, entry.object_id) == ("accounts.user", str(user.pk))
    assert (entry.before, entry.after) == ({"locale": "fr"}, {"locale": "en"})
    assert (entry.ip, entry.user_agent, entry.request_id) == ("203.0.113.7", "UA", "a" * 32)
    assert entry.reason == "demande"


def test_rg17_command_actor_is_labelled_without_user():
    entry = record("command.test", actor=COMMAND)
    assert entry.actor is None
    assert (entry.actor_kind, entry.actor_label) == (ActorKind.COMMAND, "cli:operateur")


def test_rg17_audit_rolled_back_with_business_transaction():
    """RG-17 : l'entrée est écrite dans la transaction du service ; annulée avec elle."""
    with pytest.raises(RuntimeError), transaction.atomic():
        record("role.granted", actor=COMMAND)
        raise RuntimeError("échec du service")
    assert not AuditLog.objects.exists()


@pytest.mark.parametrize("action", ["", "role", "Role.granted", "role.", "a." + "b" * 70])
def test_record_rejects_malformed_action(action):
    with pytest.raises(ValueError):
        record(action, actor=COMMAND)


@pytest.mark.parametrize("key", ["password", "secret", "token", "Token", "key"])
def test_rg17_forbidden_keys_refused_at_any_depth(key):
    with pytest.raises(AuditDataError):
        record("x.y", actor=COMMAND, after={key: "valeur"})
    with pytest.raises(AuditDataError):
        record("x.y", actor=COMMAND, before={"nested": [{key: "valeur"}]})


@pytest.mark.parametrize(
    "value",
    ["jeanne@univ.ci", "Contact : jeanne.dupont@univ.ci", "ab***c@univ.ci", "x@y"],
)
def test_rg17_clear_email_refused_in_values(value):
    """Plan §7.5 : aucune adresse e-mail en clair dans before/after, seule la forme masquée."""
    with pytest.raises(AuditDataError):
        record("x.y", actor=COMMAND, after={"email_masked": value})
    with pytest.raises(AuditDataError):
        record("x.y", actor=COMMAND, after={"items": ["ok", value]})


def test_rg17_masked_email_accepted():
    entry = record("x.y", actor=COMMAND, after={"email_masked": mask_email("jeanne@univ.ci")})
    assert entry.after == {"email_masked": "j***@univ.ci"}


@pytest.mark.parametrize(
    ("email", "masked"),
    [("jeanne.dupont@univ.ci", "j***@univ.ci"), ("a@b.org", "a***@b.org"), ("invalide", "***")],
)
def test_mask_email(email, masked):
    assert mask_email(email) == masked


def test_snapshot_uses_audit_fields_whitelist(monkeypatch):
    user = UserFactory()
    email = OutboxEmail.objects.create(
        to_email="jeanne@univ.ci",
        to_user=user,
        template_code="tests/email/plain",
        locale="fr",
        subject="Objet",
        body_text="corps",
        scheduled_at=timezone.now(),
    )
    monkeypatch.setattr(
        OutboxEmail, "AUDIT_FIELDS", ("status", "to_user", "template_code"), raising=False
    )
    assert snapshot(email) == {
        "status": "queued",
        "to_user": user.pk,
        "template_code": "tests/email/plain",
    }


def test_snapshot_requires_audit_fields():
    with pytest.raises(TypeError):
        snapshot(UserFactory())


# --- Immuabilité (plan §7.1) -----------------------------------------------------------------


def test_audit_log_is_append_only():
    entry = record("x.y", actor=COMMAND)
    entry.reason = "réécrit"
    with pytest.raises(AppendOnlyError):
        entry.save()
    with pytest.raises(AppendOnlyError):
        entry.delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=entry.pk).update(reason="réécrit")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()
    entry.refresh_from_db()
    assert entry.reason == ""


def test_purge_network_before_keeps_entries_and_is_audited():
    user = UserFactory()
    old = record("auth.login", actor=user_actor(user))
    recent = record("auth.login", actor=user_actor(user))
    cutoff = timezone.now()
    AuditLog.objects.filter(pk=old.pk)._unchecked_update(at=cutoff - timedelta(days=200))
    AuditLog.objects.filter(pk=recent.pk)._unchecked_update(at=cutoff + timedelta(seconds=1))

    assert AuditLog.purge_network_before(cutoff - timedelta(days=180), actor=COMMAND) == 1

    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.ip, old.user_agent, old.action) == (None, "", "auth.login")
    assert recent.ip == "203.0.113.7"
    purge = AuditLog.objects.get(action="audit.network_purged")
    assert purge.after["count"] == 1


def test_purge_before_deletes_old_entries_and_is_audited():
    old = record("x.y", actor=COMMAND)
    kept = record("x.y", actor=COMMAND)
    AuditLog.objects.filter(pk=old.pk)._unchecked_update(
        at=timezone.now() - timedelta(days=4 * 365)
    )
    assert AuditLog.purge_before(timezone.now() - timedelta(days=3 * 365), actor=COMMAND) == 1
    assert not AuditLog.objects.filter(pk=old.pk).exists()
    assert AuditLog.objects.filter(pk=kept.pk).exists()
    assert AuditLog.objects.get(action="audit.purged").after["count"] == 1


def test_redact_network_for_user_only_touches_that_user():
    user, other = UserFactory(), UserFactory()
    mine = record("auth.login", actor=user_actor(user))
    theirs = record("auth.login", actor=user_actor(other))
    assert AuditLog.redact_network_for_user(user, actor=COMMAND) == 1
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert (mine.ip, mine.user_agent) == (None, "")
    assert theirs.ip == "203.0.113.7"
    redaction = AuditLog.objects.get(action="audit.network_redacted")
    assert redaction.object_id == str(user.pk)
