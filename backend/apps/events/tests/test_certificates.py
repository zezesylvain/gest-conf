"""Attestations (plan L7, K9 à K11, K14, K18, K19 ; RG-16, RG-17)."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.utils import timezone
from pypdf import PdfReader

from apps.accounts.models import UserRole
from apps.accounts.roles import Role
from apps.accounts.services.personal_data import anonymize_user
from apps.accounts.services.roles import revoke_role
from apps.accounts.tests.roles_helpers import make_member
from apps.communications.models import OutboxEmail
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog, Job
from apps.events.integrity import check_certificate_files
from apps.events.models import Certificate
from apps.events.services import certificates as service
from apps.events.tests.certificate_helpers import (
    COMMAND,
    TEST_PASSWORD,
    pkcs12_file,
    present,
    signatory,
)
from apps.events.tests.certificate_helpers import (
    edition as make_edition,
)
from apps.events.tests.helpers import confirmed, participant
from apps.registrations import workflow as registration_workflow
from apps.registrations.models import RegistrationStatus
from apps.submissions.models import Submission, SubmissionAuthor
from apps.submissions.models import SubmissionStatus as S
from apps.submissions.tests.factories import author_user, complete_submission

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    return make_edition()


def text_of(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def presented(edition, submitter=None, **fields):
    submission = complete_submission(edition, submitter or author_user(first="Kofi", last="Mensah"))
    Submission.objects.filter(pk=submission.pk).update(
        status=S.PRESENTED, reference=f"{edition.code}-0042", title="Santé et climat", **fields
    )
    submission.refresh_from_db()
    return submission


def submitted_review(edition, reviewer):
    from decimal import Decimal

    from apps.reviews.models import Review, ReviewAssignment, ReviewStatus
    from apps.reviews.services.grids import create_grid

    submission = complete_submission(edition, author_user())
    grid = create_grid(edition, name="Grille", actor=COMMAND)
    assignment = ReviewAssignment.objects.create(
        submission=submission,
        reviewer=reviewer,
        assigned_at=timezone.now(),
        pseudonym_rank=1,
        active_key=f"{submission.pk}:{reviewer.pk}",
    )
    return Review.objects.create(
        assignment=assignment,
        grid=grid,
        status=ReviewStatus.SUBMITTED,
        recommendation="accept",
        confidence=3,
        comment_to_authors="Bien.",
        weighted_score=Decimal("70.00"),
        submitted_at=timezone.now(),
        version=1,
    )


# --- RG-16 : conditions par nature ---------------------------------------------------------------


def test_rg16_participation_requires_confirmed_registration_and_presence(edition):
    at_reception = present(edition)
    confirmed(edition)  # confirmée, jamais pointée
    from apps.program.models import Session

    # Fin strictement après le début (contrainte `prog_session_order`) : deux appels à
    # `timezone.now()` peuvent tomber dans la même microseconde.
    starts_at = timezone.now()
    session = Session.objects.create(
        edition=edition,
        kind="parallel",
        title_fr="Atelier",
        starts_at=starts_at,
        ends_at=starts_at + timedelta(hours=1),
    )
    in_session = present(edition, session=session)
    cancelled = present(edition)
    registration_workflow.transition(
        cancelled, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x"
    )
    users = {
        candidate.user for candidate in service.eligibility(edition, "participation").candidates
    }
    assert users == {at_reception.user, in_session.user}


def test_rg16_presentation_one_per_presenter_with_an_account(edition):
    submission = presented(edition)
    SubmissionAuthor.objects.filter(submission=submission).update(is_presenter=True)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=9,
        first_name="Sans",
        last_name="Compte",
        email="sans.compte@example.org",
        is_presenter=True,
    )
    complete_submission(edition, author_user())  # brouillon : non éligible
    found = service.eligibility(edition, "presentation")
    assert [candidate.user for candidate in found.candidates] == [submission.submitter]
    assert found.candidates[0].details == {
        "title": "Santé et climat",
        "reference": submission.reference,
    }
    assert found.unreachable == 1


def test_rg16_rg04_review_counts_only_and_is_disabled_by_default(edition):
    signatory(edition)
    reviewer = make_member(edition, Role.SC_MEMBER)
    submitted_review(edition, reviewer)
    submitted_review(edition, reviewer)
    with pytest.raises(Invalid):
        service.preflight(edition, "review")
    service.update_settings(edition, {"review_enabled": True}, actor=COMMAND)
    candidates = service.eligibility(edition, "review").candidates
    assert [(c.user, c.details) for c in candidates] == [(reviewer, {"count": 2})]


# --- K18 : signataire --------------------------------------------------------------------------


def test_k18_nothing_is_issued_without_a_designated_active_signatory(edition):
    present(edition)
    with pytest.raises(RuleViolation) as error:
        service.preflight(edition, "participation")
    assert error.value.code == "signatory_missing"
    user, _signature = signatory(edition)
    service.preflight(edition, "participation")
    revoke_role(user_role=UserRole.objects.get(user=user), actor=COMMAND, reason="Fin")
    with pytest.raises(RuleViolation) as error:
        service.preflight(edition, "participation")
    assert error.value.code == "signatory_missing"


def test_k18_only_complete_signatures_of_active_signatories_can_be_designated(edition):
    _user, signature = signatory(edition, designate=())
    other_edition = make_edition()
    _other, foreign = signatory(other_edition, designate=())
    incomplete_user = make_member(edition, Role.SIGNATORY)
    from apps.events.services import signatures

    incomplete = signatures.update_details(
        edition, incomplete_user, display_name="X", title_fr="Y", title_en="", actor=COMMAND
    )
    for bad in (foreign, incomplete):
        with pytest.raises(Invalid) as error:
            service.update_template(edition, "participation", {"signatory": bad.pk}, actor=COMMAND)
        assert "signatory" in error.value.fields
    assert [row.pk for row in service.signatories(edition)] == [signature.pk]


# --- K19 : gabarits ------------------------------------------------------------------------------


def test_k19_template_placeholders_are_closed(edition):
    with pytest.raises(Invalid) as error:
        service.update_template(
            edition,
            "participation",
            {
                "body_fr": "Merci {name} pour {title}",
                "title_en": "{name.__class__}",
                "footer_fr": "{",
            },
            actor=COMMAND,
        )
    assert set(error.value.fields) == {"body_fr", "title_en", "footer_fr"}
    view = service.update_template(
        edition, "participation", {"body_fr": "{name} était là ({dates}). {{merci}}"}, actor=COMMAND
    )
    assert view.texts["body_fr"] == "{name} était là ({dates}). {{merci}}"
    assert view.customized["body_fr"] and not view.customized["body_en"]
    # Texte vidé : retour au texte par défaut.
    view = service.update_template(edition, "participation", {"body_fr": ""}, actor=COMMAND)
    assert not view.customized["body_fr"]


def test_edition_dates_in_both_languages():
    import datetime as dt

    cases = [
        (
            (dt.date(2027, 6, 1), dt.date(2027, 6, 3)),
            "du 1er au 3 juin 2027",
            "from June 1 to 3, 2027",
        ),
        (
            (dt.date(2027, 5, 30), dt.date(2027, 6, 2)),
            "du 30 mai au 2 juin 2027",
            "from May 30 to June 2, 2027",
        ),
        ((dt.date(2027, 6, 5), dt.date(2027, 6, 5)), "le 5 juin 2027", "on June 5, 2027"),
    ]
    for (start, end), fr, en in cases:
        edition = make_edition(start_date=start, end_date=end)
        assert service.edition_dates(edition, "fr") == fr
        assert service.edition_dates(edition, "en") == en


# --- Émission (K11) ------------------------------------------------------------------------------


def test_k11_issuance_freezes_the_certificate_and_notifies(edition):
    _user, signature = signatory(edition)
    registration = present(edition, participant("Ŋgóŋ", "Łukasz-Œdipe", institution="INP-HB"))
    assert service.issue_batch(edition, "participation") == 0
    certificate = Certificate.objects.get()
    assert certificate.user == registration.user
    assert (certificate.name, certificate.institution) == ("Ŋgóŋ Łukasz-Œdipe", "INP-HB")
    assert certificate.signatory_name == "Pr Awa Diallo"
    assert certificate.signature_sha256 == signature.image_sha256
    assert certificate.signing_mode == "image"
    assert service.CODE_PATTERN.match(certificate.verification_code)
    pdf = service.pdf_bytes(certificate)
    import hashlib

    assert hashlib.sha256(pdf).hexdigest() == certificate.sha256
    text = text_of(pdf)
    assert "Ŋgóŋ Łukasz-Œdipe" in text and "du 1er au 3 juin 2027" in text
    assert "from June 1 to 3, 2027" in text
    assert certificate.verification_code in text.replace("\n", "")
    email = OutboxEmail.objects.get(template_code="events/email/certificate_available")
    assert email.to_user == registration.user
    assert "/compte/mes-documents" in email.body_text
    assert certificate.verification_code not in email.body_text
    # Idempotente : une seconde passe n'émet rien.
    assert service.issue_batch(edition, "participation") == 0
    assert Certificate.objects.count() == 1
    assert check_certificate_files() == []


def test_k11_job_runs_by_batches_and_reuses_a_pending_request(edition, monkeypatch):
    signatory(edition)
    for _ in range(3):
        present(edition)
    first = service.request_issuance(edition, "participation", actor=COMMAND)
    again = service.request_issuance(edition, "participation", actor=COMMAND)
    assert first.pk == again.pk
    monkeypatch.setattr(service, "ISSUE_BATCH", 2)
    service.issue_job(first)
    assert Certificate.objects.count() == 2
    follow_up = Job.objects.filter(kind=service.ISSUE_JOB).exclude(pk=first.pk).get()
    service.issue_job(follow_up)
    assert Certificate.objects.count() == 3
    assert AuditLog.objects.filter(action="certificates.issue_requested").count() == 1


def test_k11_job_stops_and_logs_when_conditions_are_lost(edition):
    user, _signature = signatory(edition)
    present(edition)
    job = service.request_issuance(edition, "participation", actor=COMMAND)
    revoke_role(user_role=UserRole.objects.get(user=user), actor=COMMAND, reason="Fin")
    service.issue_job(job)
    assert not Certificate.objects.exists()
    entry = AuditLog.objects.get(action="certificates.issue_failed")
    assert entry.after == {"nature": "participation", "code": "signatory_missing"}


def test_presentation_certificate_carries_the_paper(edition):
    signatory(edition)
    submission = presented(edition)
    service.issue_batch(edition, "presentation")
    certificate = Certificate.objects.get()
    assert certificate.submission == submission
    assert certificate.details == {"title": "Santé et climat", "reference": submission.reference}
    assert "Santé et climat" in text_of(service.pdf_bytes(certificate))


# --- Révocation et vérification (K10, RG-17) -----------------------------------------------------


def test_rg17_revocation_then_reissue(edition):
    signatory(edition)
    present(edition)
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    with pytest.raises(Invalid):
        service.revoke(certificate, reason=" ", actor=COMMAND)
    service.revoke(certificate, reason="Présence contestée", actor=COMMAND)
    certificate.refresh_from_db()
    assert certificate.active_key is None and certificate.revoked_at is not None
    with pytest.raises(RuleViolation):
        service.revoke(certificate, reason="Encore", actor=COMMAND)
    assert service.verify(certificate.verification_code)["status"] == "revoked"
    service.issue_batch(edition, "participation")
    assert Certificate.objects.filter(revoked_at__isnull=True).count() == 1


def test_k10_verification_is_minimal_and_not_enumerable(edition):
    signatory(edition)
    present(edition, participant("Awa", "Diallo", institution="Institut secret"))
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    data = service.verify(certificate.verification_code.lower())
    assert data["name"] == "Awa Diallo" and data["status"] == "valid"
    assert "Institut secret" not in str(data) and certificate.sha256 not in str(data)
    code = certificate.verification_code
    assert service.verify(f"{code[:5]}-{code[5:]}")["status"] == "valid"
    assert service.verify("A" * 26) is None
    assert service.verify("pas un code") is None
    assert service.verify("") is None


def test_k14_anonymized_holder_keeps_the_certificate_without_a_public_name():
    from apps.conferences.models import EditionStatus

    edition = make_edition()
    signatory(edition)
    registration = present(edition)
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    anonymize_user(registration.user, actor=COMMAND, reason="Demande")
    certificate.refresh_from_db()
    assert certificate.name  # figé, conservé (preuve délivrée)
    assert service.verify(certificate.verification_code)["name"] is None


# --- K19 : PAdES ---------------------------------------------------------------------------------


def test_k19_pades_signature_with_the_institution_certificate(edition):
    from asn1crypto import x509 as asn1_x509
    from cryptography.hazmat.primitives import serialization
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    signatory(edition)
    present(edition)
    data, x509_certificate = pkcs12_file()
    with pytest.raises(RuleViolation) as error:
        service.update_settings(edition, {"signing_mode": "pades"}, actor=COMMAND)
    assert error.value.code == "signing_unavailable"
    with pytest.raises(Invalid):
        service.upload_signing_key(edition, data=data, password="faux", actor=COMMAND)
    current = service.upload_signing_key(edition, data=data, password=TEST_PASSWORD, actor=COMMAND)
    assert current.key_subject == "CN=Université de test"
    stored = service.KEYS.read(current.key_storage_name)
    assert TEST_PASSWORD.encode() not in stored and b"Universit" not in stored  # chiffré
    service.update_settings(edition, {"signing_mode": "pades"}, actor=COMMAND)
    service.issue_batch(edition, "participation")
    certificate = Certificate.objects.get()
    assert certificate.signing_mode == "pades"
    reader = PdfFileReader(io.BytesIO(service.pdf_bytes(certificate)))
    root = asn1_x509.Certificate.load(x509_certificate.public_bytes(serialization.Encoding.DER))
    status = validate_pdf_signature(
        reader.embedded_signatures[0], ValidationContext(trust_roots=[root])
    )
    assert status.intact and status.valid and status.trusted
    # Retrait du certificat : retour à l'image seule.
    current = service.delete_signing_key(edition, actor=COMMAND)
    assert current.signing_mode == "image" and not current.key_storage_name


def test_k19_expired_certificate_and_provider_mode_are_refused(edition, settings):
    data, _certificate = pkcs12_file(days=-1)
    with pytest.raises(Invalid):
        service.upload_signing_key(edition, data=data, password=TEST_PASSWORD, actor=COMMAND)
    with pytest.raises(RuleViolation) as error:
        service.update_settings(edition, {"signing_mode": "provider"}, actor=COMMAND)
    assert error.value.code == "signing_unavailable"
    settings.GESTCONF_SIGNING_ENCRYPTION_KEYS = []
    good, _certificate = pkcs12_file()
    with pytest.raises(RuleViolation) as error:
        service.upload_signing_key(edition, data=good, password=TEST_PASSWORD, actor=COMMAND)
    assert error.value.code == "signing_unavailable"


def test_header_upload_is_used_in_documents(edition):
    from apps.events.tests.certificate_helpers import png

    current = service.upload_header(edition, data=png((1200, 200)), actor=COMMAND)
    assert (current.header_width, current.header_height) == (1200, 200)
    signatory(edition)
    assert service.preview(edition, "participation").startswith(b"%PDF")
    current = service.delete_header(edition, actor=COMMAND)
    assert not current.header_storage_name
