"""RG-19 (gel des réglages), compteur de références (F4) et données personnelles (F16)."""

from __future__ import annotations

import pytest
from django.apps import apps
from django.db import connection, transaction

from apps.accounts.roles import Role
from apps.accounts.services.personal_data import active_duties, anonymize_user, export_user_data
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.services import update_confidentiality, update_edition
from apps.core.actor import Actor
from apps.core.counters import next_value
from apps.core.errors import ErrorCode, RuleViolation
from apps.core.models import AuditLog, Counter
from apps.submissions import workflow
from apps.submissions.models import (
    StatusHistory,
    Submission,
    SubmissionAuthor,
    SubmissionRevision,
)
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import author_user, complete_submission, user_actor

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")


def submitted(edition=None, submitter=None):
    submission = complete_submission(edition, submitter)
    return workflow.transition(submission, S.SUBMITTED, user_actor(submission.submitter))


# --- RG-19 ------------------------------------------------------------------------------------


def test_rg19_drafts_do_not_freeze_settings():
    submission = complete_submission()
    edition = submission.edition
    chair = make_member(edition, Role.CHAIR)
    update_confidentiality(edition, {"double_blind": False}, actor=user_actor(chair))
    edition.refresh_from_db()
    assert edition.double_blind is False


def test_rg19_double_blind_and_code_frozen_after_first_submission():
    edition = submitted().edition
    chair = make_member(edition, Role.CHAIR)
    with pytest.raises(RuleViolation) as error:
        update_confidentiality(edition, {"double_blind": False}, actor=user_actor(chair))
    assert error.value.code == ErrorCode.SETTING_FROZEN
    with pytest.raises(RuleViolation):
        update_edition(edition, {"code": "GCX"}, actor=user_actor(chair), reason="Erreur")
    # Les autres réglages restent modifiables ; une valeur inchangée n'est pas un changement.
    update_confidentiality(
        edition, {"double_blind": True, "reviewers_per_submission": 3}, actor=user_actor(chair)
    )


def test_rg19_admin_overrides_with_a_reason_audited():
    edition = submitted().edition
    admin = make_member(edition, Role.ADMIN)
    with pytest.raises(RuleViolation):
        update_confidentiality(edition, {"double_blind": False}, actor=user_actor(admin))
    update_confidentiality(
        edition, {"double_blind": False}, actor=user_actor(admin), reason="Décision du CS"
    )
    entry = AuditLog.objects.get(action="edition.confidentiality_changed")
    assert entry.reason == "Décision du CS" and entry.after == {"double_blind": False}


def test_rg19_frozen_fields_exposed_by_the_api():
    edition = complete_submission().edition
    client = client_for(make_member(edition, Role.ADMIN))
    url = f"/v1/manage/editions/{edition.pk}/confidentiality"
    assert client.get(url).json()["frozen_fields"] == []
    workflow.transition(
        Submission.objects.get(), S.SUBMITTED, user_actor(Submission.objects.get().submitter)
    )
    assert client.get(url).json()["frozen_fields"] == ["code", "double_blind"]
    response = client.patch(url, {"double_blind": False}, format="json")
    assert response.status_code == 409 and response.json()["code"] == "setting_frozen"
    response = client.patch(url, {"double_blind": False, "reason": "Vote du CS"}, format="json")
    assert response.status_code == 200 and response.json()["double_blind"] is False
    assert "reason" not in response.json()


# --- Compteur (F4) ----------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_counter_refuses_to_run_outside_a_transaction():
    """Hors transaction, l'incrément serait validé même si l'opération échouait (trou)."""
    with pytest.raises(RuntimeError):
        next_value("x")


def test_edition_creation_creates_its_reference_counter():
    from apps.conferences.tests.factories import EditionFactory

    edition = EditionFactory()
    assert Counter.objects.get(scope=f"submission:{edition.pk}").value == 0


def test_counter_is_sequential_per_scope():
    with transaction.atomic():
        assert [next_value("x"), next_value("x"), next_value("y")] == [1, 2, 1]
    assert Counter.objects.get(scope="x").value == 2


@pytest.mark.mariadb_only  # SQLite verrouille la base entière : sans objet
@pytest.mark.django_db(transaction=True)
def test_counter_has_no_duplicate_under_concurrency():
    """F4 : soumissions simultanées, numéros distincts et consécutifs (verrou de ligne)."""
    import threading

    from apps.core.counters import ensure_counter

    ensure_counter("submission:CONC")  # comme à la création de l'édition
    values: list[int] = []
    errors: list[str] = []

    def take() -> None:
        try:
            with transaction.atomic():
                values.append(next_value("submission:CONC"))
        except Exception as error:  # pragma: no cover - diagnostic du test
            errors.append(repr(error))
        finally:
            connection.close()

    threads = [threading.Thread(target=take) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(20)
    assert errors == []
    assert sorted(values) == list(range(1, 9))


# --- Données personnelles (F16, RG-18) --------------------------------------------------------


def test_rg18_active_submission_blocks_anonymization():
    submission = submitted()
    user = submission.submitter
    assert active_duties(user) == [f"submission:{submission.reference}"]
    with pytest.raises(RuleViolation) as error:
        anonymize_user(user, actor=COMMAND, reason="Demande")
    assert error.value.code == ErrorCode.ACCOUNT_HAS_ACTIVE_DUTIES
    # Archivée : plus de responsabilité.
    Submission.objects.get().edition.__class__.objects.update(status=EditionStatus.ARCHIVED)
    assert active_duties(user) == []


def test_rg18_export_contains_own_submissions_and_authorships():
    submission = submitted()
    colleague = author_user(first="Koffi", last="Yao")
    SubmissionAuthor.objects.create(
        submission=submission,
        position=2,
        user=colleague,
        first_name="Koffi",
        last_name="Yao",
        email=colleague.email,
    )
    own = export_user_data(submission.submitter, actor=COMMAND)
    assert own["submissions"][0]["reference"] == submission.reference
    assert [a["last_name"] for a in own["submissions"][0]["authors"]] == ["Zadi", "Yao"]
    theirs = export_user_data(colleague, actor=COMMAND)
    assert theirs["authorships"] == [
        {"reference": submission.reference, "title": submission.title, "position": 2}
    ]


def _text_values(model) -> list[str]:
    from django.db import models

    fields = [
        field.attname
        for field in model._meta.concrete_fields
        if isinstance(field, models.CharField | models.TextField | models.JSONField)
    ]
    return [str(v) for row in model.objects.values_list(*fields) for v in row] if fields else []


def test_rg18_anonymization_sweeps_submissions():
    """Brouillons supprimés ; ailleurs (retirée), nom et adresses absents de toute colonne
    texte des tables de soumission, clichés et motifs compris."""
    user = author_user(first="Zéphyrine", last="Kpangbalo", email="zk@univ-test.ci")
    complete_submission(submitter=user)  # brouillon
    withdrawn = submitted(submitter=user)
    SubmissionRevision.objects.create(
        submission=withdrawn,
        number=1,
        at=withdrawn.submitted_at,
        actor=user,
        snapshot={"authors": [{"name": "Zéphyrine Kpangbalo", "email": "zk@univ-test.ci"}]},
    )
    workflow.transition(
        withdrawn, S.WITHDRAWN, user_actor(user), reason="Zéphyrine Kpangbalo se retire"
    )
    anonymize_user(user, actor=COMMAND, reason="Demande")
    assert list(Submission.objects.values_list("status", flat=True)) == [S.WITHDRAWN]
    needles = ["zk@univ-test.ci", "zéphyrine", "kpangbalo"]
    leaks = []
    for model in apps.get_app_config("submissions").get_models():
        for value in _text_values(model):
            leaks += [(model._meta.label, n) for n in needles if n in value.lower()]
    assert leaks == []
    assert StatusHistory.objects.get(to_status=S.WITHDRAWN).reason == "Anonyme se retire"


# --- Intégrité ------------------------------------------------------------------------------


def test_integrity_checks_detect_anomalies():
    from apps.submissions import integrity
    from apps.submissions.models import SubmissionFile

    submission = submitted()
    assert integrity.check_reference_sequence() == []
    Submission.objects.filter(pk=submission.pk).update(reference=f"{submission.edition.code}-0007")
    assert integrity.check_reference_sequence() == [
        f"Références {submission.edition.code} : 1 attribuées, compteur à 1."
    ]
    for version in (1, 2):
        SubmissionFile.objects.create(
            submission=submission,
            kind="main",
            version=version,
            storage_name=f"{version:032x}",
            original_name="a.pdf",
            size=1,
            sha256="0" * 64,
            pages=1,
            uploaded_by=submission.submitter,
        )
    assert len(integrity.check_current_files()) == 1
    assert len(integrity.check_missing_files()) == 2
