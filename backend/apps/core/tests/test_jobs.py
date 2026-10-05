"""File de tâches (règle n° 9, plan L1 §8.2 et §12.1 « Tâches »)."""

import time
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.core import jobs
from apps.core.models import Job, JobPriority, JobStatus

pytestmark = pytest.mark.django_db

calls: list[int] = []
final_failures: list[int] = []


@jobs.register_job("tests.record")
def _record_handler(job):
    calls.append(job.payload["n"])


def _final_failure(job):
    final_failures.append(job.pk)


@jobs.register_job("tests.fail", on_final_failure=_final_failure)
def _failing_handler(job):
    raise RuntimeError("message pouvant contenir jeanne@univ.ci")


@jobs.register_job("tests.defer")
def _deferring_handler(job):
    raise jobs.RetryLater(timezone.now() + timedelta(minutes=10))


@pytest.fixture(autouse=True)
def _reset_calls():
    calls.clear()
    final_failures.clear()


def far_deadline() -> float:
    return time.monotonic() + 60


def test_enqueue_refuses_unknown_kind_and_non_json_payload():
    with pytest.raises(ValueError):
        jobs.enqueue("tests.unknown")
    with pytest.raises(TypeError):
        jobs.enqueue("tests.record", {"when": timezone.now()})


def test_enqueue_with_dedup_key_returns_existing_job():
    first = jobs.enqueue("tests.record", {"n": 1}, dedup_key="tests:1")
    second = jobs.enqueue("tests.record", {"n": 2}, dedup_key="tests:1")
    assert first.pk == second.pk
    assert Job.objects.count() == 1


def test_claim_is_exclusive():
    """Deux exécutants ne réservent jamais le même job (mise à jour conditionnelle)."""
    job = jobs.enqueue("tests.record", {"n": 1})
    assert jobs.claim(job.pk, "hote:1") is True
    assert jobs.claim(job.pk, "hote:2") is False
    job.refresh_from_db()
    assert (job.status, job.locked_by, job.attempts) == (JobStatus.RUNNING, "hote:1", 1)


def test_claim_ignores_jobs_not_yet_due():
    job = jobs.enqueue("tests.record", {"n": 1}, run_at=timezone.now() + timedelta(minutes=5))
    assert jobs.claim(job.pk, "hote:1") is False


def test_execute_success_marks_job_succeeded():
    job = jobs.enqueue("tests.record", {"n": 7})
    assert jobs.claim(job.pk, "w")
    assert jobs.execute(job.pk, "w") == JobStatus.SUCCEEDED
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert job.finished_at is not None
    assert (job.locked_by, job.locked_at) == ("", None)
    assert calls == [7]


def test_execute_requires_own_reservation():
    job = jobs.enqueue("tests.record", {"n": 1})
    assert jobs.claim(job.pk, "w1")
    assert jobs.execute(job.pk, "w2") is None
    assert calls == []


def test_failure_is_retried_with_increasing_delays_and_no_personal_data():
    job = jobs.enqueue("tests.fail", max_attempts=5)
    delays = []
    for expected in jobs.RETRY_DELAYS:
        Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
        assert jobs.claim(job.pk, "w")
        before = timezone.now()
        assert jobs.execute(job.pk, "w") == JobStatus.PENDING
        job.refresh_from_db()
        delays.append(job.run_at - before)
        assert expected <= job.run_at - before < expected + timedelta(seconds=5)
    assert delays == sorted(delays)
    # Nature de l'erreur seulement : le message de l'exception n'est pas conservé.
    assert job.last_error == "builtins.RuntimeError"
    assert "@" not in job.last_error


def test_job_fails_after_max_attempts_and_alerts(settings):
    settings.ADMINS = [("Opérateur", "ops@example.org")]
    job = jobs.enqueue("tests.fail", max_attempts=2)
    for _attempt in range(2):
        Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
        assert jobs.claim(job.pk, "w")
        jobs.execute(job.pk, "w")
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.attempts == 2
    assert job.finished_at is not None
    assert final_failures == [job.pk]
    assert len(mail.outbox) == 1
    assert "tests.fail" in mail.outbox[0].body
    assert "jeanne" not in mail.outbox[0].body


def test_retry_later_does_not_consume_an_attempt():
    job = jobs.enqueue("tests.defer")
    assert jobs.claim(job.pk, "w")
    assert jobs.execute(job.pk, "w") == JobStatus.PENDING
    job.refresh_from_db()
    assert job.attempts == 0
    assert job.run_at > timezone.now() + timedelta(minutes=9)


def test_unregistered_kind_fails_immediately():
    job = Job.objects.create(kind="tests.removed", run_at=timezone.now())
    assert jobs.claim(job.pk, "w")
    assert jobs.execute(job.pk, "w") == JobStatus.FAILED


def test_recover_stale_requeues_expired_lease():
    job = jobs.enqueue("tests.record", {"n": 1})
    assert jobs.claim(job.pk, "w")
    Job.objects.filter(pk=job.pk).update(
        locked_at=timezone.now() - jobs.LEASE_DURATION - timedelta(seconds=1)
    )
    assert jobs.recover_stale() == 1
    job.refresh_from_db()
    assert (job.status, job.locked_by, job.attempts) == (JobStatus.PENDING, "", 1)


def test_recover_stale_keeps_fresh_lease():
    job = jobs.enqueue("tests.record", {"n": 1})
    assert jobs.claim(job.pk, "w")
    assert jobs.recover_stale() == 0
    job.refresh_from_db()
    assert job.status == JobStatus.RUNNING


def test_recover_stale_fails_job_out_of_attempts():
    job = jobs.enqueue("tests.fail", max_attempts=1)
    assert jobs.claim(job.pk, "w")
    Job.objects.filter(pk=job.pk).update(locked_at=timezone.now() - timedelta(hours=1))
    assert jobs.recover_stale() == 1
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert final_failures == [job.pk]


def test_run_pending_processes_by_priority_then_date():
    jobs.enqueue("tests.record", {"n": 3}, priority=JobPriority.BULK)
    jobs.enqueue("tests.record", {"n": 2})
    jobs.enqueue("tests.record", {"n": 1}, priority=JobPriority.URGENT)
    assert jobs.run_pending(deadline=far_deadline(), batch_size=2) == 3
    assert calls == [1, 2, 3]


def test_run_pending_respects_time_budget():
    jobs.enqueue("tests.record", {"n": 1})
    assert jobs.run_pending(deadline=time.monotonic() - 1) == 0
    assert calls == []


def test_run_pending_twice_has_no_double_effect():
    jobs.enqueue("tests.record", {"n": 1})
    jobs.run_pending(deadline=far_deadline())
    jobs.run_pending(deadline=far_deadline())
    assert calls == [1]


def test_try_run_now_never_raises(monkeypatch):
    job = jobs.enqueue("tests.record", {"n": 1})

    def broken_claim(*args, **kwargs):
        raise RuntimeError("base indisponible")

    monkeypatch.setattr(jobs, "claim", broken_claim)
    assert jobs.try_run_now(job.pk) is None


def test_register_job_refuses_conflicting_handler():
    with pytest.raises(ValueError):
        jobs.register_job("tests.record")(lambda job: None)
