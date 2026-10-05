"""Commandes cron verrouillées (plan L1 §8.2, §8.4, §12.1) : run_jobs, cleanup, verrous."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core import mail
from django.core.cache import caches
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from apps.core import jobs
from apps.core.cache_maintenance import purge_expired_cache_entries
from apps.core.locking import command_lock
from apps.core.management.base import LockedCommand
from apps.core.models import AuditLog, CronHeartbeat, HeartbeatStatus, Job, JobStatus

pytestmark = pytest.mark.django_db

processed_ids: list[int] = []


@jobs.register_job("tests.commands.record")
def _record(job):
    processed_ids.append(job.pk)


@pytest.fixture(autouse=True)
def _reset():
    processed_ids.clear()


def run(name, *args, **options):
    out = StringIO()
    call_command(name, *args, stdout=out, **options)
    return out.getvalue()


# --- LockedCommand ------------------------------------------------------------------------


@pytest.mark.parametrize("command", ["run_jobs", "cleanup"])
def test_locked_command_exits_cleanly_when_lock_is_taken(command):
    job = jobs.enqueue("tests.commands.record")
    with command_lock(command) as acquired:
        assert acquired
        output = run(command)
    assert "une autre exécution est en cours" in output
    assert not CronHeartbeat.objects.filter(name=command).exists()
    job.refresh_from_db()
    assert job.status == JobStatus.PENDING


def test_lock_is_released_after_use():
    with command_lock("run_jobs") as first:
        assert first
    with command_lock("run_jobs") as second:
        assert second


def test_lock_name_is_validated():
    with pytest.raises(ValueError), command_lock("../evil"):
        pass


@pytest.mark.mariadb_only
def test_database_lock_is_exclusive(settings):
    """Repli GET_LOCK (H-5) : un second preneur sur une autre connexion est refusé."""
    from django.db import connections

    settings.GESTCONF_COMMAND_LOCK = "database"
    other = connections.create_connection("default")
    try:
        with command_lock("run_jobs") as acquired:
            assert acquired
            with other.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK('gestconf.run_jobs', 0)")
                assert cursor.fetchone()[0] == 0
        with other.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK('gestconf.run_jobs', 0)")
            assert cursor.fetchone()[0] == 1
            cursor.execute("SELECT RELEASE_LOCK('gestconf.run_jobs')")
    finally:
        other.close()


def test_heartbeat_records_success():
    jobs.enqueue("tests.commands.record")
    jobs.enqueue("tests.commands.record")
    run("run_jobs", max_seconds=30)
    beat = CronHeartbeat.objects.get(name="run_jobs")
    assert beat.last_status == HeartbeatStatus.OK
    assert beat.processed_count == 2
    assert beat.last_success_at is not None
    assert beat.last_duration_ms is not None
    assert len(processed_ids) == 2


class _BrokenCommand(LockedCommand):
    lock_name = "broken"

    def run(self, *args, **options):
        raise RuntimeError("panne")


def test_heartbeat_records_error_and_alerts(settings):
    settings.ADMINS = [("Opérateur", "ops@example.org")]
    with pytest.raises(RuntimeError):
        _BrokenCommand().handle(verbosity=0)
    beat = CronHeartbeat.objects.get(name="broken")
    assert beat.last_status == HeartbeatStatus.ERROR
    assert beat.last_success_at is None
    assert beat.last_error == "builtins.RuntimeError"
    assert len(mail.outbox) == 1


# --- run_jobs -----------------------------------------------------------------------------


def test_run_jobs_twice_has_no_double_effect():
    jobs.enqueue("tests.commands.record")
    run("run_jobs")
    run("run_jobs")
    assert len(processed_ids) == 1


def test_run_jobs_recovers_stale_jobs():
    job = jobs.enqueue("tests.commands.record")
    assert jobs.claim(job.pk, "mort:1")
    Job.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(hours=1))
    run("run_jobs")
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert processed_ids == [job.pk]


def test_run_jobs_respects_time_budget():
    jobs.enqueue("tests.commands.record")
    run("run_jobs", max_seconds=0)
    assert processed_ids == []


@pytest.mark.mariadb
def test_purge_expired_cache_entries_in_both_tables():
    for alias in ("default", "throttle"):
        store = caches[alias]
        store.set("tests:expired", 1, timeout=60)
        store.set("tests:alive", 1, timeout=60)
        table = connection.ops.quote_name(store._table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET expires = %s WHERE cache_key LIKE %s",  # noqa: S608
                [
                    connection.ops.adapt_datetimefield_value(timezone.now() - timedelta(minutes=1)),
                    "%tests:expired",
                ],
            )
    assert purge_expired_cache_entries() == {"default": 1, "throttle": 1}
    for alias in ("default", "throttle"):
        assert caches[alias].get("tests:alive") == 1


# --- cleanup ------------------------------------------------------------------------------


def _finished_job(days_ago):
    job = jobs.enqueue("tests.commands.record")
    Job.objects.filter(pk=job.pk).update(
        status=JobStatus.SUCCEEDED, finished_at=timezone.now() - timedelta(days=days_ago)
    )
    return job


def test_cleanup_simulates_unvalidated_retention(settings):
    """D15 non validée : comptage seul, rien n'est supprimé ; résumé audité."""
    settings.GESTCONF_RETENTION_ENFORCED = False
    old = _finished_job(40)
    output = run("cleanup")
    assert Job.objects.filter(pk=old.pk).exists()
    assert "core.finished_jobs -> 1 (simulation)" in output
    entry = AuditLog.objects.get(action="retention.applied")
    assert entry.actor_label == "cron:cleanup"
    assert entry.after["tasks"]["core.finished_jobs"] == {"count": 1, "dry_run": True}


def test_cleanup_applies_retention_when_enforced_and_is_idempotent(settings):
    settings.GESTCONF_RETENTION_ENFORCED = True
    old = _finished_job(40)
    recent = _finished_job(5)
    run("cleanup")
    assert not Job.objects.filter(pk=old.pk).exists()
    assert Job.objects.filter(pk=recent.pk).exists()
    run("cleanup")
    assert Job.objects.filter(pk=recent.pk).exists()
    assert CronHeartbeat.objects.get(name="cleanup").last_status == HeartbeatStatus.OK
