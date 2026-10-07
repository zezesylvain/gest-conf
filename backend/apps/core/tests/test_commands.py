"""Commandes d'exploitation (plan L1 §8.2, §8.4, §9.4) : verrou, battement de cœur,
run_jobs, cleanup."""

import errno
import fcntl
import io
import os
from datetime import timedelta

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.core.cache import caches
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.utils import timezone

from apps.core import jobs, locks
from apps.core.actor import Actor
from apps.core.audit import AuditAction, record
from apps.core.locks import CommandLock, LockMechanism, db_lock_name
from apps.core.models import AuditLog, CronHeartbeat, HeartbeatStatus, Job, JobStatus

pytestmark = pytest.mark.django_db

# Toutes les commandes d'exploitation héritent de LockedCommand ; arguments minimaux.
OPERATION_COMMANDS = [
    ("run_jobs", []),
    ("cleanup", []),
    ("send_test_email", ["--to", "ops@example.org"]),
    ("outbox", []),
]


def run(name, *args):
    out = io.StringIO()
    call_command(name, *args, stdout=out)
    return out.getvalue()


def hold_flock(settings, name):
    """Prend le verrou fichier de la commande comme le ferait une autre exécution."""
    lock_dir = settings.GESTCONF_LOCK_DIR
    lock_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_dir / f"{name}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


# --- LockedCommand : sortie propre quand le verrou est pris ----------------------------------


@pytest.mark.parametrize(("name", "args"), OPERATION_COMMANDS)
def test_command_exits_cleanly_when_lock_is_taken(settings, name, args):
    """Verrou déjà pris : la commande s'arrête sans erreur (code 0) et ne fait rien."""
    from apps.communications.models import OutboxEmail

    fd = hold_flock(settings, name)
    try:
        output = run(name, *args)
    finally:
        os.close(fd)
    assert "déjà en cours" in output
    assert not CronHeartbeat.objects.exists()
    assert not OutboxEmail.objects.exists()
    assert not AuditLog.objects.exists()


def test_command_runs_once_the_lock_is_released(settings):
    fd = hold_flock(settings, "run_jobs")
    os.close(fd)  # verrou libéré par la fermeture
    assert "déjà en cours" not in run("run_jobs")
    assert CronHeartbeat.objects.get(name="run_jobs").last_status == HeartbeatStatus.SUCCEEDED


def test_lock_is_released_after_a_failure(settings, monkeypatch):
    monkeypatch.setattr(
        "apps.core.management.commands.run_jobs.process_jobs",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("panne")),
    )
    with pytest.raises(RuntimeError):
        run("run_jobs")
    lock = CommandLock("run_jobs", settings.GESTCONF_LOCK_DIR)
    assert lock.acquire() is True
    assert lock.mechanism == LockMechanism.FLOCK
    lock.release()


def test_flock_is_exclusive_between_two_holders(settings):
    first = CommandLock("demo", settings.GESTCONF_LOCK_DIR)
    second = CommandLock("demo", settings.GESTCONF_LOCK_DIR)
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()


def _flock_unavailable(monkeypatch):
    def broken(fd, operation):
        raise OSError(errno.ENOLCK, "No locks available")

    monkeypatch.setattr(locks.fcntl, "flock", broken)


@pytest.mark.skipif(connection.vendor == "mysql", reason="repli propre à SQLite")
def test_without_flock_nor_get_lock_the_command_runs_unlocked(settings, monkeypatch, caplog):
    """R6 : sans aucun verrou, la commande s'exécute quand même (réservation exclusive)."""
    _flock_unavailable(monkeypatch)
    lock = CommandLock("demo", settings.GESTCONF_LOCK_DIR)
    assert lock.acquire() is True
    assert lock.mechanism == LockMechanism.NONE
    assert "sans verrou" in caplog.text
    lock.release()


def test_unwritable_lock_dir_falls_back(settings, monkeypatch, tmp_path):
    blocker = tmp_path / "fichier"
    blocker.write_text("x")
    lock = CommandLock("demo", blocker / "sous-dossier")  # mkdir impossible
    assert lock.acquire() is True
    assert lock.mechanism in {LockMechanism.GET_LOCK, LockMechanism.NONE}
    lock.release()


@pytest.mark.mariadb_only
def test_get_lock_fallback_when_flock_fails(settings, monkeypatch):
    """flock indisponible : repli sur GET_LOCK, exclusif entre deux connexions MariaDB."""
    _flock_unavailable(monkeypatch)
    name = db_lock_name("run_jobs")
    assert name.startswith("gestconf.") and len(name) <= 64
    raw = connection.get_new_connection(connection.get_connection_params())
    try:
        with raw.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 0)", [name])
            assert cursor.fetchone()[0] == 1
        output = run("run_jobs")
        assert "déjà en cours" in output
        assert not CronHeartbeat.objects.exists()
        with raw.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", [name])
    finally:
        raw.close()
    lock = CommandLock("run_jobs", settings.GESTCONF_LOCK_DIR)
    assert lock.acquire() is True
    assert lock.mechanism == LockMechanism.GET_LOCK
    lock.release()
    with connection.cursor() as cursor:
        cursor.execute("SELECT IS_FREE_LOCK(%s)", [name])
        assert cursor.fetchone()[0] == 1


def test_db_lock_name_is_bounded(monkeypatch):
    monkeypatch.setitem(connection.settings_dict, "NAME", "x" * 80)
    name = db_lock_name("run_jobs")
    assert len(name) <= 64 and name.startswith("gestconf.")


# --- Battement de cœur ---------------------------------------------------------------------


def test_heartbeat_records_start_and_end():
    run("run_jobs")
    beat = CronHeartbeat.objects.get(name="run_jobs")
    assert beat.last_status == HeartbeatStatus.SUCCEEDED
    assert beat.last_started_at <= beat.last_finished_at == beat.last_success_at
    assert beat.last_duration_ms is not None
    assert beat.processed_count == 0
    assert set(beat.summary) == {"recovered", "purges"}


def test_heartbeat_records_failure_without_success(monkeypatch):
    run("run_jobs")
    success = CronHeartbeat.objects.get(name="run_jobs").last_success_at
    monkeypatch.setattr(
        "apps.core.management.commands.run_jobs.process_jobs",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("panne pour jean@univ.ci")),
    )
    with pytest.raises(RuntimeError):
        run("run_jobs")
    beat = CronHeartbeat.objects.get(name="run_jobs")
    assert beat.last_status == HeartbeatStatus.FAILED
    assert beat.last_success_at == success
    assert "j***@univ.ci" in beat.last_error


def test_cron_commands_are_not_audited_on_each_run():
    """Arbitrage L1.2 : la trace des commandes cron est le battement de cœur, pas l'audit."""
    run("run_jobs")
    run("cleanup")
    assert not AuditLog.objects.exists()


# --- run_jobs ------------------------------------------------------------------------------


def test_run_jobs_processes_pending_jobs():
    calls = []
    jobs.register_job("tests.cmd")(lambda payload, context: calls.append(payload))
    try:
        for index in range(3):
            jobs.enqueue("tests.cmd", {"n": index})
        output = run("run_jobs", "--max-seconds", "30")
    finally:
        jobs.unregister_job("tests.cmd")
    assert len(calls) == 3
    assert "Tâches exécutées : 3" in output
    assert CronHeartbeat.objects.get(name="run_jobs").processed_count == 3


def test_run_jobs_recovers_stale_jobs_first():
    jobs.register_job("tests.cmd")(lambda payload, context: None)
    try:
        job = jobs.enqueue("tests.cmd")
        Job.objects.filter(pk=job.pk).update(
            status=JobStatus.RUNNING,
            locked_at=timezone.now() - timedelta(minutes=20),
            locked_by="mort:1",
            attempts=1,
        )
        run("run_jobs")
    finally:
        jobs.unregister_job("tests.cmd")
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert job.attempts == 2


@pytest.mark.parametrize("value", ["0", "-5"])
def test_run_jobs_rejects_non_positive_budget(value):
    with pytest.raises(CommandError):
        run("run_jobs", "--max-seconds", value)


def test_run_jobs_default_budget_follows_cron_interval(settings, monkeypatch):
    seen = {}

    def fake_process(**kwargs):
        seen.update(kwargs)
        return 0

    settings.GESTCONF_CRON_INTERVAL_SECONDS = 60
    monkeypatch.setattr("apps.core.management.commands.run_jobs.process_jobs", fake_process)
    run("run_jobs")
    assert seen["max_seconds"] == 48


def _expire_cache_entries():
    """Une entrée expirée et une valide dans chacune des deux tables de cache."""
    for alias in ("default", "throttle"):
        caches[alias].set(f"valide-{alias}", 1, timeout=300)
        caches[alias].set(f"expiree-{alias}", 1, timeout=300)
    past = connection.ops.adapt_datetimefield_value(
        (timezone.now() - timedelta(minutes=1)).replace(microsecond=0)
    )
    with connection.cursor() as cursor:
        for table in ("gestconf_cache", "gestconf_throttle_cache"):
            cursor.execute(
                f"UPDATE {table} SET expires = %s WHERE cache_key LIKE %s",  # noqa: S608
                [past, "%expiree%"],
            )


def _cache_keys():
    with connection.cursor() as cursor:
        keys = []
        for table in ("gestconf_cache", "gestconf_throttle_cache"):
            cursor.execute(f"SELECT cache_key FROM {table}")  # noqa: S608 (nom fixe)
            keys += [row[0] for row in cursor.fetchall()]
    return sorted(key.rsplit(":", 1)[-1] for key in keys)


@pytest.mark.mariadb
def test_run_jobs_purges_expired_entries_of_both_cache_tables():
    """R18, §16 point 4 : les entrées expirées des DEUX tables disparaissent à chaque passage."""
    _expire_cache_entries()
    run("run_jobs")
    assert _cache_keys() == ["valide-default", "valide-throttle"]
    purges = CronHeartbeat.objects.get(name="run_jobs").summary["purges"]
    assert purges["core.cache_expired_entries"] == {
        "category": "security",
        "mode": "applied",
        "count": 2,
    }


def test_cache_purge_uses_table_names_from_settings(settings):
    """Noms tirés de CACHES (cités) : une table renommée est purgée sous son nouveau nom."""
    from apps.core.retention import _database_cache_tables

    assert _database_cache_tables() == [
        ("default", "gestconf_cache"),
        ("throttle", "gestconf_throttle_cache"),
    ]


def test_run_jobs_reports_a_failing_purge_without_failing(monkeypatch):
    from apps.core import retention

    rule = retention._rules["core.cache_expired_entries"]

    def broken(now, actor):
        raise RuntimeError("table absente")

    monkeypatch.setitem(
        retention._rules,
        rule.name,
        retention.RetentionRule(rule.name, rule.category, rule.count, broken, with_jobs=True),
    )
    run("run_jobs")
    beat = CronHeartbeat.objects.get(name="run_jobs")
    assert beat.last_status == HeartbeatStatus.SUCCEEDED
    assert "core.cache_expired_entries" in beat.last_error


# --- cleanup -------------------------------------------------------------------------------


def _old_audit_entries():
    actor = Actor(kind="user", ip="203.0.113.9", user_agent="UA")
    entry = record(AuditAction.COMMAND_SEND_TEST_EMAIL, actor=actor)
    AuditLog.objects.filter(pk=entry.pk)._privileged_update(
        at=timezone.now() - timedelta(days=1200)
    )
    return entry


def _old_finished_job():
    jobs.register_job("tests.cmd")(lambda payload, context: None)
    try:
        job = jobs.enqueue("tests.cmd")
    finally:
        jobs.unregister_job("tests.cmd")
    Job.objects.filter(pk=job.pk).update(
        status=JobStatus.SUCCEEDED, finished_at=timezone.now() - timedelta(days=31)
    )
    return job


def _expired_session():
    store = SessionStore()
    store["x"] = 1
    store.create()
    Session.objects.filter(session_key=store.session_key).update(
        expire_date=timezone.now() - timedelta(minutes=1)
    )


def test_cleanup_simulates_legal_purges_by_default(settings):
    """D15 non validée (Q14) : les purges légales sont simulées, la sécurité est appliquée."""
    settings.GESTCONF_RETENTION_ENFORCE = False
    entry = _old_audit_entries()
    job = _old_finished_job()
    _expired_session()
    output = run("cleanup")
    assert AuditLog.objects.filter(pk=entry.pk, ip="203.0.113.9").exists()
    assert Job.objects.filter(pk=job.pk).exists()
    assert not Session.objects.exists()  # sécurité : toujours appliquée
    assert AuditLog.objects.count() == 1  # aucune trace retention.applied en simulation
    rules = CronHeartbeat.objects.get(name="cleanup").summary["rules"]
    assert rules["core.audit_entries"] == {"category": "legal", "mode": "simulated", "count": 1}
    assert rules["core.audit_network_context"]["count"] == 1
    assert rules["core.finished_jobs"] == {"category": "legal", "mode": "simulated", "count": 1}
    assert rules["core.sessions_expired"] == {"category": "security", "mode": "applied", "count": 1}
    assert "seraient purgés (simulation)" in output


def test_cleanup_applies_legal_purges_when_enforced_and_audits(settings):
    settings.GESTCONF_RETENTION_ENFORCE = True
    entry = _old_audit_entries()
    job = _old_finished_job()
    run("cleanup")
    assert not AuditLog.objects.filter(pk=entry.pk).exists()
    assert not Job.objects.filter(pk=job.pk).exists()
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert AuditAction.RETENTION_APPLIED in actions
    applied = AuditLog.objects.get(action=AuditAction.RETENTION_APPLIED)
    assert applied.actor_label == "job:cleanup"
    assert applied.after["core.audit_entries"] == 1
    assert applied.after["core.finished_jobs"] == 1
    # Idempotente : un second passage ne trouve plus rien.
    run("cleanup")
    rules = CronHeartbeat.objects.get(name="cleanup").summary["rules"]
    assert all(entry["count"] == 0 for entry in rules.values())


def test_cleanup_dry_run_overrides_enforcement(settings):
    settings.GESTCONF_RETENTION_ENFORCE = True
    entry = _old_audit_entries()
    run("cleanup", "--dry-run")
    assert AuditLog.objects.filter(pk=entry.pk).exists()
    assert not AuditLog.objects.filter(action=AuditAction.RETENTION_APPLIED).exists()


def test_cleanup_fails_its_heartbeat_when_a_rule_fails(monkeypatch):
    from apps.core import retention

    rule = retention._rules["core.sessions_expired"]

    def broken(now, actor):
        raise RuntimeError("panne")

    monkeypatch.setitem(
        retention._rules,
        rule.name,
        retention.RetentionRule(rule.name, rule.category, rule.count, broken),
    )
    with pytest.raises(CommandError):
        run("cleanup")
    beat = CronHeartbeat.objects.get(name="cleanup")
    assert beat.last_status == HeartbeatStatus.FAILED
    assert beat.summary["rules"]["core.sessions_expired"]["error"] == "RuntimeError"
    # Les autres règles ont tourné malgré tout.
    assert "core.cache_expired_entries" in beat.summary["rules"]


def test_retention_durations_match_d15():
    from apps.core import retention

    assert timedelta(hours=24) == retention.SENSITIVE_EMAIL_BODY_MAX_AGE
    assert timedelta(days=30) == retention.EMAIL_BODY_RETENTION
    assert timedelta(days=365) <= retention.EMAIL_METADATA_RETENTION
    assert timedelta(days=182) <= retention.AUDIT_NETWORK_RETENTION
    assert timedelta(days=3 * 365) <= retention.AUDIT_RETENTION
    assert timedelta(days=30) == retention.FINISHED_JOB_RETENTION


def test_only_security_rules_run_with_jobs():
    from apps.core.retention import RetentionCategory, RetentionRule, register_rule

    with pytest.raises(ValueError):
        register_rule(
            RetentionRule("x.y", RetentionCategory.LEGAL, lambda n: 0, lambda n, a: 0, True)
        )
