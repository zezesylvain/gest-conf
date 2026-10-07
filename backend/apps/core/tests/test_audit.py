"""Journal d'audit (RG-17, plan L1 §7) : écriture, liste blanche, immuabilité, purges nommées."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, connection, models, transaction
from django.test import RequestFactory
from django.test.utils import isolate_apps
from django.utils import timezone

from apps.core.actor import Actor, ActorKind
from apps.core.audit import (
    AuditAction,
    contains_clear_email,
    mask_email,
    record,
    snapshot,
)
from apps.core.models import AppendOnlyError, AuditLog, Job

pytestmark = pytest.mark.django_db

OPERATOR = Actor.command("cli:operateur")


def user_actor(user, ip="203.0.113.7", agent="Navigateur/1.0"):
    request = RequestFactory().get("/", REMOTE_ADDR=ip, HTTP_USER_AGENT=agent)
    request.user = user if user is not None else AnonymousUser()
    request.request_id = "f" * 32
    return Actor.from_request(request)


# --- record ---------------------------------------------------------------------------------


def test_record_user_actor_with_network_context(user):
    entry = record(
        AuditAction.COMMAND_SEND_TEST_EMAIL,
        actor=user_actor(user),
        obj=user,
        after={"locale": "fr"},
        reason="  essai  ",
    )
    entry.refresh_from_db()
    assert entry.actor == user
    assert entry.actor_kind == ActorKind.USER
    assert entry.actor_label == ""
    assert entry.action == "command.send_test_email"
    assert (entry.object_type, entry.object_id) == ("accounts.user", str(user.pk))
    assert entry.after == {"locale": "fr"}
    assert entry.before is None
    assert entry.reason == "essai"
    assert entry.request_id == "f" * 32
    assert entry.ip == "203.0.113.7"
    assert entry.user_agent == "Navigateur/1.0"


def test_record_command_actor_has_label_and_no_user():
    entry = record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=OPERATOR)
    assert entry.actor is None
    assert entry.actor_kind == ActorKind.COMMAND
    assert entry.actor_label == "cli:operateur"
    assert entry.ip is None
    assert (entry.object_type, entry.object_id) == ("", "")


def test_record_refuses_unknown_action():
    with pytest.raises(ValueError):
        record("role.granted_typo", actor=OPERATOR)
    assert not AuditLog.objects.exists()


def test_record_refuses_unsaved_object():
    with pytest.raises(ValueError, match="enregistré"):
        record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=OPERATOR, obj=Job(kind="x.y"))


@pytest.mark.parametrize("key", ["password", "secret", "token", "Password"])
def test_rg17_record_refuses_forbidden_keys_at_any_depth(key):
    """RG-17 : jamais de mot de passe, de secret ni de jeton dans before/after."""
    with pytest.raises(ValueError, match="Clés interdites"):
        record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=OPERATOR, after={key: "x"})
    with pytest.raises(ValueError, match="Clés interdites"):
        record(
            AuditAction.COMMAND_SEND_TEST_EMAIL,
            actor=OPERATOR,
            before={"profile": [{"nested": {key: "x"}}]},
        )
    assert not AuditLog.objects.exists()


def test_record_accepts_keys_that_only_contain_forbidden_words():
    """Égalité stricte (plan §7.5) : « email_masked » ou « token_expired » restent permis."""
    entry = record(
        AuditAction.COMMAND_SEND_TEST_EMAIL,
        actor=OPERATOR,
        after={"email_masked": "j***@univ.ci", "token_expired": True},
    )
    assert entry.after["email_masked"] == "j***@univ.ci"


@pytest.mark.parametrize(
    "state",
    [
        {"to": "jean.dupont@univ.ci"},
        {"nested": {"list": ["ok", "Contact : jean@univ.ci"]}},
        {"mixed": "j***@univ.ci et marie@univ.ci"},
    ],
)
def test_rg17_record_refuses_clear_email_in_values(state):
    """RG-17 : aucune adresse en clair, à n'importe quel niveau des valeurs (plan §7.5 v4)."""
    with pytest.raises(ValueError, match="en clair"):
        record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=OPERATOR, after=state)
    assert not AuditLog.objects.exists()


def test_record_requires_reason_for_sensitive_action():
    with pytest.raises(ValueError, match="Motif obligatoire"):
        record(AuditAction.COMMAND_OUTBOX_RETRY, actor=OPERATOR, reason="   ")
    assert not AuditLog.objects.exists()


def test_record_serializes_dates_and_decimals():
    from decimal import Decimal

    at = timezone.now()
    entry = record(
        AuditAction.COMMAND_SEND_TEST_EMAIL,
        actor=OPERATOR,
        after={"at": at, "score": Decimal("12.50")},
    )
    entry.refresh_from_db()
    assert entry.after["score"] == "12.50"
    assert entry.after["at"].startswith(at.date().isoformat())


def test_rg17_audit_rolled_back_with_business_transaction():
    """RG-17 : record() s'exécute dans la transaction de l'appelant ; une action annulée
    ne laisse aucune trace, ni de l'objet métier ni de l'audit."""

    class BusinessError(Exception):
        pass

    with pytest.raises(BusinessError), transaction.atomic():
        from apps.core.jobs import enqueue, register_job, unregister_job

        register_job("tests.rollback")(lambda payload, context: None)
        try:
            job = enqueue("tests.rollback", {"n": 1})
            record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=OPERATOR, obj=job)
            assert AuditLog.objects.count() == 1
            raise BusinessError
        finally:
            unregister_job("tests.rollback")
    assert not AuditLog.objects.exists()
    assert not Job.objects.exists()


# --- Masquage et détection des adresses ---------------------------------------------------


@pytest.mark.parametrize(
    ("address", "masked"),
    [
        ("jean.dupont@univ.ci", "j***@univ.ci"),
        ("  A@b.org ", "A***@b.org"),
        ("sans-arobase", "***"),
        ("@domaine.ci", "***@domaine.ci"),
    ],
)
def test_mask_email(address, masked):
    assert mask_email(address) == masked
    assert not contains_clear_email(masked)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("j***@univ.ci", False),
        ("x***@d", False),
        ("aucune adresse", False),
        ("jean@univ.ci", True),
        ("j*@univ.ci et paul@x.org", True),
        (["ok", {"k": "a@b.c"}], True),
        ({"k": ("a", 1, None)}, False),
        (42, False),
    ],
)
def test_contains_clear_email(value, expected):
    assert contains_clear_email(value) is expected


# --- snapshot : liste blanche AUDIT_FIELDS --------------------------------------------------


def _model(name, fields, audit_fields=None):
    """Modèle jetable, hors du registre global (isolate_apps) : aucun effet sur les méta-tests."""
    attrs = {"__module__": __name__, "Meta": type("Meta", (), {"app_label": "core"}), **fields}
    if audit_fields is not None:
        attrs["AUDIT_FIELDS"] = audit_fields
    return type(name, (models.Model,), attrs)


@isolate_apps("apps.core")
def test_snapshot_requires_audit_fields():
    unlisted = _model("Unlisted", {"label": models.CharField(max_length=10)})
    with pytest.raises(ImproperlyConfigured, match="AUDIT_FIELDS"):
        snapshot(unlisted(label="x"))


@isolate_apps("apps.core")
def test_snapshot_refuses_email_field():
    with_email = _model("WithEmail", {"contact": models.EmailField()}, ("contact",))
    with pytest.raises(ImproperlyConfigured, match="adresse e-mail en clair"):
        snapshot(with_email(contact="a@b.org"))


@isolate_apps("apps.core")
def test_snapshot_refuses_forbidden_field_names():
    with_secret = _model("WithSecret", {"token": models.CharField(max_length=10)}, ("token",))
    with pytest.raises(ImproperlyConfigured, match="token"):
        snapshot(with_secret(token="x"))


def test_snapshot_keeps_only_listed_fields_and_masks_email(user):
    from apps.communications.models import OutboxEmail

    email = OutboxEmail.objects.create(
        to_email="jean.dupont@univ.ci",
        to_user=user,
        template_code="communications.test_email",
        locale="fr",
        subject="Objet",
        body_text="Corps contenant un lien secret",
    )
    state = snapshot(email)
    assert set(state) == set(OutboxEmail.AUDIT_FIELDS)
    assert state["to_user"] == user.pk
    assert state["to_email_masked"] == "j***@univ.ci"
    assert "subject" not in state and "body_text" not in state
    assert not contains_clear_email(state)


def test_every_audited_model_has_a_safe_whitelist():
    """Méta-test : aucun AUDIT_FIELDS ne contient d'EmailField ni de nom interdit."""
    from django.apps import apps

    from apps.core.audit import FORBIDDEN_KEYS

    for model in apps.get_models():
        names = getattr(model, "AUDIT_FIELDS", None)
        if not names:
            continue
        for name in names:
            assert name.lower() not in FORBIDDEN_KEYS, (model, name)
            field = next((f for f in model._meta.get_fields() if f.name == name), None)
            assert not isinstance(field, models.EmailField), (model, name)


# --- Immuabilité (ajout seul) ---------------------------------------------------------------


@pytest.fixture
def entry():
    return record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=user_actor(None))


def test_rg17_audit_log_save_update_is_refused(entry):
    entry.reason = "réécriture"
    with pytest.raises(AppendOnlyError):
        entry.save()
    entry.refresh_from_db()
    assert entry.reason == ""


def test_rg17_audit_log_delete_is_refused(entry):
    with pytest.raises(AppendOnlyError):
        entry.delete()
    assert AuditLog.objects.filter(pk=entry.pk).exists()


def test_rg17_audit_log_queryset_update_and_delete_are_refused(entry):
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.filter(pk=entry.pk).update(reason="x")
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.all().delete()
    with pytest.raises(AppendOnlyError):
        AuditLog.objects.bulk_update([entry], ["reason"])
    assert AuditLog.objects.count() == 1


def test_audit_log_reinsert_with_existing_pk_fails(entry):
    clone = AuditLog(pk=entry.pk, actor_kind="system", actor_label="job:x", action="audit.purged")
    with pytest.raises(IntegrityError), transaction.atomic():
        clone.save()


# --- Méthodes nommées, elles-mêmes auditées -----------------------------------------------


def _old_entry(user, days):
    entry = record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=user_actor(user))
    AuditLog.objects.filter(pk=entry.pk)._privileged_update(
        at=timezone.now() - timedelta(days=days)
    )
    return entry


def test_purge_network_before_keeps_the_log_and_is_audited(user):
    """La purge du contexte réseau laisse le journal intact (plan §7.5)."""
    old = _old_entry(user, 200)
    recent = _old_entry(user, 10)
    cutoff = timezone.now() - timedelta(days=183)
    assert AuditLog.objects.purge_network_before(cutoff, actor=OPERATOR) == 1
    old.refresh_from_db()
    recent.refresh_from_db()
    assert (old.ip, old.user_agent, old.action, old.actor) == (None, "", old.action, user)
    assert recent.ip == "203.0.113.7"
    trace = AuditLog.objects.get(action=AuditAction.AUDIT_NETWORK_PURGED)
    assert trace.after == {"cutoff": cutoff.isoformat(), "count": 1}
    assert trace.actor_label == "cli:operateur"
    # Idempotente : rien de plus au second passage.
    assert AuditLog.objects.purge_network_before(cutoff, actor=OPERATOR) == 0


def test_purge_before_deletes_old_entries_and_is_audited(user):
    _old_entry(user, 1200)
    recent = _old_entry(user, 10)
    cutoff = timezone.now() - timedelta(days=1096)
    assert AuditLog.objects.purge_before(cutoff, actor=OPERATOR) == 1
    remaining = set(AuditLog.objects.values_list("action", flat=True))
    assert remaining == {recent.action, AuditAction.AUDIT_PURGED}
    assert AuditLog.objects.get(action=AuditAction.AUDIT_PURGED).after["count"] == 1


def test_redact_network_for_user_including_its_own_trace(user):
    """Anonymisation en libre-service : le compte agit lui-même ; même la ligne qui trace
    l'effacement ne garde pas son IP."""
    from apps.accounts.tests.factories import UserFactory

    other = UserFactory()
    mine = _old_entry(user, 1)
    theirs = _old_entry(other, 1)
    assert AuditLog.objects.redact_network_for_user(user, actor=user_actor(user)) == 1
    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert (mine.ip, mine.user_agent) == (None, "")
    assert theirs.ip == "203.0.113.7"
    trace = AuditLog.objects.get(action=AuditAction.AUDIT_NETWORK_REDACTED)
    assert (trace.object_type, trace.object_id) == ("accounts.user", str(user.pk))
    assert trace.after == {"count": 1}
    assert (trace.ip, trace.user_agent) == (None, "")


def test_named_methods_are_atomic(user, monkeypatch):
    """Si l'audit de la purge échoue, la purge est annulée (même transaction)."""
    from apps.core import audit

    _old_entry(user, 200)

    def failing_record(*args, **kwargs):
        raise RuntimeError("audit indisponible")

    monkeypatch.setattr(audit, "record", failing_record)
    with pytest.raises(RuntimeError):
        AuditLog.objects.purge_network_before(timezone.now(), actor=OPERATOR)
    assert AuditLog.objects.filter(ip__isnull=False).count() == 1


# --- Contraintes en base ----------------------------------------------------------------------


def test_actor_consistency_constraint_rejects_command_without_label():
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog(actor_kind=ActorKind.COMMAND, actor_label="", action="audit.purged").save()


def test_actor_kind_constraint_rejects_unknown_kind():
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditLog(actor_kind="robot", actor_label="x", action="audit.purged").save()


@pytest.mark.mariadb_only
def test_check_constraints_exist_in_mariadb():
    """Plan §3.1 : les contraintes CHECK sont bien créées par MariaDB (introspection)."""
    expected = {
        "core_auditlog": {"core_audit_actor_kind_valid", "core_audit_actor_consistent"},
        "core_job": {
            "core_job_status_valid",
            "core_job_max_attempts_positive",
            "core_job_dedup_key_not_blank",
        },
        "core_cronheartbeat": {"core_heartbeat_status_valid"},
        "communications_outboxemail": {
            "comm_outbox_status_valid",
            "comm_outbox_idempotency_key_not_blank",
        },
    }
    with connection.cursor() as cursor:
        for table, names in expected.items():
            constraints = connection.introspection.get_constraints(cursor, table)
            checks = {name for name, info in constraints.items() if info["check"]}
            assert names <= checks, (table, checks)
