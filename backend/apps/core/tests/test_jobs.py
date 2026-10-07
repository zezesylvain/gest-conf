"""File de tâches (plan L1 §8.2) : mise en file, réservation exclusive, reprises, budget."""

import threading
from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection, connections, transaction
from django.utils import timezone

from apps.core import jobs
from apps.core.jobs import (
    JobContext,
    JobDeferred,
    JobOutcome,
    enqueue,
    process_jobs,
    recover_stale_jobs,
    register_job,
    retry_delay,
    run_job,
    safe_error_text,
)
from apps.core.models import Job, JobStatus

KIND = "tests.work"


class Recorder:
    """Gestionnaire de test : note chaque exécution, peut échouer ou reporter sur commande."""

    def __init__(self) -> None:
        self.calls: list[tuple[dict, JobContext]] = []
        self.failures_left = 0
        self.defer_to = None
        self.lock = threading.Lock()

    def __call__(self, payload: dict, context: JobContext) -> None:
        with self.lock:
            self.calls.append((payload, context))
        if self.defer_to is not None:
            raise JobDeferred(self.defer_to, "test")
        if self.failures_left:
            self.failures_left -= 1
            raise RuntimeError("échec voulu pour jean.dupont@univ.ci")


@pytest.fixture
def recorder():
    handler = Recorder()
    failed_payloads: list[dict] = []
    register_job(KIND, on_final_failure=failed_payloads.append)(handler)
    handler.failed_payloads = failed_payloads
    yield handler
    jobs.unregister_job(KIND)


# --- Registre et mise en file -------------------------------------------------------------


@pytest.mark.parametrize("kind", ["sansPoint", "Majuscule.verbe", "a." + "x" * 70, ".vide"])
def test_register_job_validates_kind(kind):
    with pytest.raises(ValueError):
        register_job(kind)


def test_register_job_refuses_a_second_handler(recorder):
    with pytest.raises(ValueError, match="déjà enregistré"):
        register_job(KIND)(lambda payload, context: None)


def test_send_email_kind_is_registered():
    assert "communications.send_email" in jobs.registered_kinds()


@pytest.mark.django_db
def test_enqueue_defaults(recorder):
    job = enqueue(KIND, {"outbox_id": 3, "ids": (1, 2)})
    job.refresh_from_db()
    assert job.status == JobStatus.PENDING
    assert job.payload == {"outbox_id": 3, "ids": [1, 2]}
    assert (job.priority, job.attempts, job.max_attempts) == (100, 0, 5)
    assert job.dedup_key is None
    assert job.run_at <= timezone.now()


@pytest.mark.django_db
def test_enqueue_unknown_kind_is_refused():
    with pytest.raises(ValueError, match="inconnu"):
        enqueue("tests.unknown")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {"password": "x"},
        {"api_token": "x"},
        {"client_secret": "x"},
        {"to": "jean@univ.ci"},
        {"nested": {"a": 1}},
        {"objects": [object()]},
        {1: "clé non textuelle"},
    ],
)
def test_enqueue_payload_has_ids_and_scalars_only(recorder, payload):
    """Identifiants et scalaires seulement, jamais de secret ni d'adresse (§3.5)."""
    with pytest.raises((TypeError, ValueError)):
        enqueue(KIND, payload)
    assert not Job.objects.exists()


@pytest.mark.django_db
def test_enqueue_with_dedup_key_is_idempotent(recorder):
    first = enqueue(KIND, {"n": 1}, dedup_key="work:1")
    second = enqueue(KIND, {"n": 2}, dedup_key="work:1")
    assert first.pk == second.pk
    assert Job.objects.count() == 1


@pytest.mark.django_db
def test_enqueue_dedup_key_used_by_another_kind_is_refused(recorder):
    enqueue(KIND, dedup_key="work:1")
    register_job("tests.other")(lambda payload, context: None)
    try:
        with pytest.raises(ValueError, match="autre type"):
            enqueue("tests.other", dedup_key="work:1")
    finally:
        jobs.unregister_job("tests.other")


@pytest.mark.django_db
@pytest.mark.parametrize("key", ["", "x" * 129, "email:jean@univ.ci"])
def test_enqueue_invalid_dedup_key(recorder, key):
    with pytest.raises(ValueError):
        enqueue(KIND, dedup_key=key)


@pytest.mark.django_db
def test_enqueue_happens_in_the_caller_transaction(recorder):
    """Schéma transactional outbox : une action annulée ne laisse aucune tâche."""
    with pytest.raises(RuntimeError), transaction.atomic():
        enqueue(KIND, {"n": 1}, dedup_key="work:rollback")
        raise RuntimeError
    assert not Job.objects.exists()


@pytest.mark.django_db
def test_enqueue_dedup_race_does_not_break_the_caller_transaction(recorder, monkeypatch):
    """Doublon concurrent (IntegrityError) : point de sauvegarde, tâche existante renvoyée."""
    existing = enqueue(KIND, dedup_key="work:race")
    original_filter = Job.objects.filter

    def blind_filter(*args, **kwargs):
        if kwargs.get("dedup_key") == "work:race":
            return Job.objects.none()
        return original_filter(*args, **kwargs)

    monkeypatch.setattr(Job.objects, "filter", blind_filter)
    with transaction.atomic():
        again = enqueue(KIND, dedup_key="work:race")
        assert again.pk == existing.pk
        assert Job.objects.count() == 1  # la transaction reste utilisable


# --- Exécution, reprises, échec définitif -------------------------------------------------


@pytest.mark.django_db
def test_run_job_success(recorder):
    job = enqueue(KIND, {"n": 1})
    assert run_job(job.pk, worker="hote:1") == JobOutcome.SUCCEEDED
    job.refresh_from_db()
    assert (job.status, job.attempts, job.locked_by) == (JobStatus.SUCCEEDED, 1, "hote:1")
    assert job.finished_at is not None
    payload, context = recorder.calls[0]
    assert payload == {"n": 1}
    assert (context.attempt, context.max_attempts, context.fast_path) == (1, 5, False)


@pytest.mark.django_db
def test_run_job_is_never_executed_twice(recorder):
    """Idempotence par double exécution : une tâche terminée n'est plus réservable."""
    job = enqueue(KIND)
    assert run_job(job.pk, worker="a:1") == JobOutcome.SUCCEEDED
    assert run_job(job.pk, worker="b:2") is None
    assert len(recorder.calls) == 1


@pytest.mark.django_db
def test_run_job_ignores_future_jobs(recorder):
    job = enqueue(KIND, run_at=timezone.now() + timedelta(minutes=5))
    assert run_job(job.pk, worker="a:1") is None
    assert recorder.calls == []


@pytest.mark.parametrize(
    ("attempts", "delay"),
    [
        (1, timedelta(minutes=1)),
        (2, timedelta(minutes=5)),
        (3, timedelta(minutes=30)),
        (4, timedelta(hours=2)),
        (9, timedelta(hours=2)),
    ],
)
def test_retry_delays_grow(attempts, delay):
    assert retry_delay(attempts) == delay


@pytest.mark.django_db
def test_failure_retries_with_backoff_then_fails_definitively(recorder, operator_emails):
    """1 min, 5 min, 30 min, 2 h, puis échec définitif après max_attempts, avec alerte."""
    recorder.failures_left = 99
    job = enqueue(KIND, {"n": 7}, max_attempts=5)
    expected = [
        timedelta(minutes=1),
        timedelta(minutes=5),
        timedelta(minutes=30),
        timedelta(hours=2),
    ]
    for attempt, delay in enumerate(expected, start=1):
        before = timezone.now()
        assert run_job(job.pk, worker="a:1") == JobOutcome.RETRY
        job.refresh_from_db()
        assert (job.status, job.attempts, job.locked_by) == (JobStatus.PENDING, attempt, "")
        assert before + delay <= job.run_at <= timezone.now() + delay
        # Le message d'erreur est conservé, adresse masquée.
        assert "j***@univ.ci" in job.last_error and "jean.dupont" not in job.last_error
        Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
    assert mail.outbox == []
    assert run_job(job.pk, worker="a:1") == JobOutcome.FAILED
    job.refresh_from_db()
    assert (job.status, job.attempts) == (JobStatus.FAILED, 5)
    assert job.finished_at is not None
    assert recorder.failed_payloads == [{"n": 7}]
    assert len(mail.outbox) == 1
    alert = mail.outbox[0]
    assert alert.to == operator_emails
    assert f"#{job.pk}" in alert.body and KIND in alert.body and "RuntimeError" in alert.body
    assert "jean" not in alert.body  # jamais le message de l'exception
    # Échec définitif : plus jamais exécutée.
    Job.objects.filter(pk=job.pk).update(run_at=timezone.now())
    assert run_job(job.pk, worker="a:1") is None


@pytest.mark.django_db
def test_unregistered_kind_fails_definitively(recorder):
    job = enqueue(KIND)
    jobs.unregister_job(KIND)
    assert run_job(job.pk, worker="a:1") == JobOutcome.FAILED
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert "LookupError" in job.last_error


@pytest.mark.django_db
def test_deferral_does_not_consume_an_attempt(recorder):
    later = timezone.now() + timedelta(minutes=17)
    recorder.defer_to = later
    job = enqueue(KIND)
    assert run_job(job.pk, worker="a:1") == JobOutcome.DEFERRED
    job.refresh_from_db()
    assert (job.status, job.attempts, job.run_at, job.locked_by) == (
        JobStatus.PENDING,
        0,
        later,
        "",
    )


@pytest.mark.django_db
def test_safe_error_text_masks_addresses_and_truncates():
    text = safe_error_text(ValueError("refusé : <jean.dupont@univ.ci> ; " + "x" * 3000))
    assert text.startswith("ValueError: refusé : <j***@univ.ci>")
    assert len(text) == 2000


# --- Bail expiré ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_recover_stale_jobs(recorder, operator_emails):
    now = timezone.now()
    stale = enqueue(KIND)
    exhausted = enqueue(KIND, max_attempts=2)
    fresh = enqueue(KIND)
    Job.objects.filter(pk=stale.pk).update(
        status=JobStatus.RUNNING, locked_at=now - timedelta(minutes=16), locked_by="x:1", attempts=1
    )
    Job.objects.filter(pk=exhausted.pk).update(
        status=JobStatus.RUNNING, locked_at=now - timedelta(minutes=16), locked_by="x:1", attempts=2
    )
    Job.objects.filter(pk=fresh.pk).update(
        status=JobStatus.RUNNING, locked_at=now - timedelta(minutes=14), locked_by="x:1", attempts=1
    )
    assert recover_stale_jobs(now=now) == {"requeued": 1, "failed": 1}
    statuses = dict(Job.objects.values_list("pk", "status"))
    assert statuses == {
        stale.pk: JobStatus.PENDING,
        exhausted.pk: JobStatus.FAILED,
        fresh.pk: JobStatus.RUNNING,
    }
    assert recorder.failed_payloads == [{}]
    assert len(mail.outbox) == 1
    # L'ancien exécutant, s'il se réveille, ne peut plus rien écrire sur la tâche.
    assert jobs._mine(stale.pk, "x:1").update(status=JobStatus.SUCCEEDED) == 0


# --- Boucle et budget de temps --------------------------------------------------------------


@pytest.mark.django_db
def test_process_jobs_order_and_budget(recorder):
    later = enqueue(KIND, {"n": "bulk"}, priority=200)
    urgent = enqueue(KIND, {"n": "urgent"}, priority=0)
    normal = enqueue(KIND, {"n": "normal"})
    ticks = iter([0.0, 0.0, 0.0, 0.0, 10.0, 10.0, 10.0])
    processed = process_jobs(max_seconds=5, worker="a:1", clock=lambda: next(ticks))
    assert processed == 2
    assert [payload["n"] for payload, _ in recorder.calls] == ["urgent", "normal"]
    later.refresh_from_db()
    assert later.status == JobStatus.PENDING  # budget épuisé : commencera au passage suivant
    assert {urgent.pk, normal.pk} == set(
        Job.objects.filter(status=JobStatus.SUCCEEDED).values_list("pk", flat=True)
    )


@pytest.mark.django_db
def test_process_jobs_batches_and_stops_when_queue_is_empty(recorder):
    for index in range(45):
        enqueue(KIND, {"n": index})
    assert process_jobs(max_seconds=60, worker="a:1", batch_size=20) == 45
    assert len(recorder.calls) == 45
    assert process_jobs(max_seconds=60, worker="a:1") == 0


@pytest.mark.django_db
def test_process_jobs_does_not_loop_on_a_job_rescheduled_in_the_past(recorder):
    recorder.defer_to = timezone.now() - timedelta(seconds=1)
    enqueue(KIND)
    assert process_jobs(max_seconds=60, worker="a:1") == 1
    assert len(recorder.calls) == 1


@pytest.mark.django_db
def test_process_jobs_twice_has_no_double_effect(recorder):
    """Intégration (§12.3) : deux passages de suite, aucune tâche exécutée deux fois."""
    for index in range(5):
        enqueue(KIND, {"n": index})
    assert process_jobs(max_seconds=60, worker="a:1") == 5
    assert process_jobs(max_seconds=60, worker="b:2") == 0
    assert sorted(payload["n"] for payload, _ in recorder.calls) == list(range(5))


# --- Concurrence réelle : deux connexions MariaDB, sans verrou de commande -------------------


@pytest.mark.mariadb_only
@pytest.mark.django_db(transaction=True)
def test_conditional_reservation_is_exclusive_across_two_connections(recorder):
    """Deux exécutants simultanés (deux fils, donc deux connexions MariaDB) sur les mêmes
    tâches, sans LockedCommand : chaque tâche est exécutée exactement une fois (§8.2)."""
    total = 40
    for index in range(total):
        enqueue(KIND, {"n": index})
    barrier = threading.Barrier(2)
    results: dict[str, int] = {}
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            barrier.wait()
            results[name] = process_jobs(max_seconds=60, worker=name, batch_size=total)
        except BaseException as exc:  # remonté au fil principal
            errors.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("w:1", "w:2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert errors == []
    executed = [payload["n"] for payload, _ in recorder.calls]
    assert sorted(executed) == list(range(total))  # chacune une fois, aucune deux fois
    assert results["w:1"] + results["w:2"] == total
    assert Job.objects.filter(status=JobStatus.SUCCEEDED).count() == total


@pytest.mark.mariadb_only
@pytest.mark.django_db(transaction=True)
def test_reservation_update_loses_against_a_committed_reservation(recorder):
    """La même tâche réservée depuis une seconde connexion brute : la réservation de Django
    ne modifie aucune ligne et le gestionnaire n'est pas appelé."""
    job = enqueue(KIND)
    raw = connection.get_new_connection(connection.get_connection_params())
    try:
        with raw.cursor() as cursor:
            cursor.execute(
                "UPDATE core_job SET status='running', locked_by='autre:1', attempts=attempts+1 "
                "WHERE id=%s AND status='pending'",
                [job.pk],
            )
            assert cursor.rowcount == 1
        raw.commit()
    finally:
        raw.close()
    assert run_job(job.pk, worker="w:1") is None
    assert recorder.calls == []
    job.refresh_from_db()
    assert (job.locked_by, job.attempts) == ("autre:1", 1)
