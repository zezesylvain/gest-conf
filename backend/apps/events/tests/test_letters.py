"""Lettres d'invitation (plan L7, K12, K14) et inscription au comptoir (K13)."""

from __future__ import annotations

import datetime as dt
import io

import pytest
from allauth.account.models import EmailAddress
from django.utils import timezone
from pypdf import PdfReader
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.conferences.models import EditionStatus
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.events.integrity import check_letter_files
from apps.events.models import InvitationLetter, LetterStatus
from apps.events.services import certificates, letters
from apps.events.tests.certificate_helpers import COMMAND, signatory
from apps.events.tests.certificate_helpers import edition as make_edition
from apps.events.tests.helpers import confirmed, participant
from apps.events.tests.letter_helpers import PASSPORT
from apps.registrations import workflow as registration_workflow
from apps.registrations.models import RegistrationStatus
from apps.registrations.tests.factories import make_category, make_registration

pytestmark = pytest.mark.django_db


@pytest.fixture
def edition():
    return make_edition()


def text_of(pdf: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)


def requested(edition, **fields):
    registration = make_registration(edition, participant(), status=RegistrationStatus.PENDING)
    return letters.request_letter(registration, {**PASSPORT, **fields}, actor=COMMAND)


# --- Service ------------------------------------------------------------------------------------


def test_k12_request_rules(edition):
    letter = requested(edition)
    assert letter.status == LetterStatus.REQUESTED
    with pytest.raises(RuleViolation):  # une demande à la fois
        letters.request_letter(letter.registration, PASSPORT, actor=COMMAND)
    with pytest.raises(Invalid):
        requested(edition, stay_to=dt.date(2027, 5, 1))
    with pytest.raises(Invalid):
        requested(edition, stay_to=dt.date(2027, 9, 30))
    cancelled = make_registration(edition, participant(), status=RegistrationStatus.CANCELLED)
    with pytest.raises(RuleViolation):
        letters.request_letter(cancelled, PASSPORT, actor=COMMAND)
    # Jamais de numéro de passeport au journal (K14).
    entry = AuditLog.objects.get(action="letter.requested")
    assert "A12345678" not in str(entry.after)


def test_k12_issue_renders_signed_letter_and_notifies(edition):
    signatory(edition)
    letter = letters.issue_letter(requested(edition), actor=COMMAND)
    assert letter.status == LetterStatus.ISSUED
    assert certificates.CODE_PATTERN.match(letter.verification_code)
    pdf = letters.pdf_bytes(letter)
    reader = PdfReader(io.BytesIO(pdf))
    width, height = (float(v) * 25.4 / 72 for v in reader.pages[0].mediabox[2:])
    assert (round(width), round(height)) == (210, 297)  # A4 portrait
    text = text_of(pdf)
    for expected in ("DIALLO Awa", "A12345678", "du 31 mai au 4 juin 2027", "Dakar"):
        assert expected in text
    assert "n'engage pas la prise en charge" in text
    email = OutboxEmail.objects.get(template_code="events/email/letter_issued")
    assert "A12345678" not in email.body_text
    assert check_letter_files() == []
    verified = certificates.verify(letter.verification_code)
    assert (verified["kind"], verified["name"], verified["status"]) == (
        "letter",
        "DIALLO Awa",
        "valid",
    )
    letters.revoke_letter(letter, reason="Inscription annulée", actor=COMMAND)
    assert certificates.verify(letter.verification_code)["status"] == "revoked"


def test_k12_issue_requires_a_letter_signatory(edition):
    letter = requested(edition)
    with pytest.raises(RuleViolation) as error:
        letters.issue_letter(letter, actor=COMMAND)
    assert error.value.code == "signatory_missing"
    signatory(edition, designate=("participation",))  # pas pour les lettres
    with pytest.raises(RuleViolation):
        letters.issue_letter(letter, actor=COMMAND)


def test_k12_refusal_allows_a_new_request(edition):
    letter = requested(edition)
    with pytest.raises(Invalid):
        letters.refuse_letter(letter, reason="", actor=COMMAND)
    letters.refuse_letter(letter, reason="Dates incohérentes", actor=COMMAND)
    email = OutboxEmail.objects.get(template_code="events/email/letter_refused")
    assert "Dates incohérentes" in email.body_text
    again = letters.request_letter(letter.registration, PASSPORT, actor=COMMAND)
    assert again.status == LetterStatus.REQUESTED
    assert letters.current_letter(letter.registration) == again


def test_k12_cancelled_registration_blocks_issuance(edition):
    signatory(edition)
    registration = confirmed(edition)
    letter = letters.request_letter(registration, PASSPORT, actor=COMMAND)
    registration_workflow.transition(
        registration, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x"
    )
    with pytest.raises(RuleViolation):
        letters.issue_letter(letter, actor=COMMAND)


def test_k14_passport_numbers_are_erased_after_the_edition(edition):
    letter = requested(edition)
    now = timezone.now()
    assert letters.erase_passport_numbers(True, now) == 0
    edition.start_date = (now - dt.timedelta(days=33)).date()
    edition.end_date = (now - dt.timedelta(days=31)).date()
    edition.save()
    assert letters.erase_passport_numbers(True, now) == 1  # simulation : rien n'est effacé
    letter.refresh_from_db()
    assert letter.passport_number == "A12345678"
    assert letters.erase_passport_numbers(False, now) == 1
    letter.refresh_from_db()
    assert (letter.passport_number, letter.passport_erased_at) == ("", now)


def test_k14_export_and_anonymization(edition):
    signatory(edition)
    letter = letters.issue_letter(requested(edition), actor=COMMAND)
    user = letter.registration.user
    exported = export_user_data(user, actor=COMMAND)["invitation_letters"]
    assert exported[0]["passport_number"] == "A12345678"
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    registration = letter.registration
    registration_workflow.transition(registration, RegistrationStatus.EXPIRED, actor=COMMAND)
    anonymize_user(user, actor=COMMAND, reason="Demande")
    letter.refresh_from_db()
    assert letter.passport_number == "" and letter.passport_name == "DIALLO Awa"
    assert certificates.verify(letter.verification_code)["name"] is None


# --- API ----------------------------------------------------------------------------------------


def payload(**fields):
    return {
        **PASSPORT,
        "stay_from": "2027-05-31",
        "stay_to": "2027-06-04",
        **fields,
    }


def test_k12_participant_api(edition):
    signatory(edition)
    user = participant()
    registration = make_registration(edition, user, status=RegistrationStatus.PENDING)
    client = client_for(user, mfa=False)
    path = f"/v1/registrations/{registration.pk}/invitation-letter"
    assert client.get(path).status_code == 404
    response = client.post(path, payload(), format="json")
    assert response.status_code == 201, response.content
    body = response.json()
    assert body["passport_number_masked"] == "••••••678"
    assert "passport_number" not in body
    assert client.get(f"{path}/pdf").status_code == 404  # pas encore émise
    letters.issue_letter(InvitationLetter.objects.get(), actor=COMMAND)
    response = client.get(f"{path}/pdf")
    assert response.status_code == 200 and response["Cache-Control"] == "private, no-store"
    assert client.get(path).json()["status"] == "issued"
    stranger = client_for(participant(), mfa=False)
    assert stranger.get(path).status_code == 404
    assert APIClient().get(path).status_code == 401


def test_k12_manage_api(edition):
    signatory(edition)
    letter = requested(edition)
    manager = client_for(make_member(edition, Role.OC_MEMBER, oc_function="external_relations"))
    base = f"/v1/manage/editions/{edition.pk}/invitation-letters"
    rows = manager.get(f"{base}?status=requested").json()["results"]
    assert [row["id"] for row in rows] == [letter.pk]
    assert "passport_number" not in rows[0]
    detail = manager.get(f"{base}/{letter.pk}").json()
    assert detail["passport_number"] == "A12345678"
    body = manager.post(f"{base}/{letter.pk}/issue").json()
    assert body["status"] == "issued" and body["signatory_name"] == "Pr Awa Diallo"
    assert manager.get(f"{base}/{letter.pk}/pdf").status_code == 200
    body = manager.post(f"{base}/{letter.pk}/revoke", {"reason": "Erreur"}, format="json").json()
    assert body["status"] == "revoked"
    volunteer = client_for(make_member(edition, Role.VOLUNTEER))
    assert volunteer.get(base).status_code == 403


# --- Comptoir (K13) -----------------------------------------------------------------------------


def test_k13_counter_creates_a_passwordless_account_and_confirms_on_payment(edition):
    from decimal import Decimal

    from apps.conferences.models import KeyDate
    from apps.registrations.models import Fee

    # Le jour J : inscriptions closes, tarif « sur place » (J2).
    KeyDate.objects.create(
        edition=edition, code="registration_open", at=timezone.now() - dt.timedelta(days=60)
    )
    KeyDate.objects.create(
        edition=edition, code="registration_close", at=timezone.now() - dt.timedelta(days=1)
    )
    category = make_category(edition, "sur-place", label_fr="Sur place")
    for period in ("early", "regular", "onsite"):
        for zone in ("local", "international"):
            Fee.objects.create(category=category, period=period, zone=zone, amount=Decimal("10000"))
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    response = client.post(
        f"/v1/manage/editions/{edition.pk}/registrations/counter",
        {
            "email": "Nouvelle.Personne@Example.org",
            "first_name": "Yaa",
            "last_name": "Asantewaa",
            "institution": "Université du Ghana",
            "country": "GH",
            "category": "sur-place",
            "paid": True,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    body = response.json()
    assert (body["status"], body["account_created"]) == ("confirmed", True)
    user = User.objects.get(email__iexact="nouvelle.personne@example.org")
    assert not user.has_usable_password()
    assert not EmailAddress.objects.get(user=user).verified
    assert user.profile.last_name == "Asantewaa"
    assert AuditLog.objects.filter(action="registrations.counter_created").count() == 1
    reset = OutboxEmail.objects.filter(to_user=user, template_code__contains="password_reset")
    assert reset.count() == 1
    # Badge imprimable aussitôt.
    badge = client.get(
        f"/v1/manage/editions/{edition.pk}/registrations/{body['registration_id']}/badge"
    )
    assert badge.status_code == 200
    # Adresse connue : rattachée au compte existant, sans nouveau lien.
    known = participant()
    response = client.post(
        f"/v1/manage/editions/{edition.pk}/registrations/counter",
        {"email": known.email, "category": "sur-place"},
        format="json",
    )
    assert response.json()["account_created"] is False
    assert response.json()["status"] == "pending"
    assert OutboxEmail.objects.filter(template_code__contains="password_reset").count() == 1


def test_k13_counter_refuses_deactivated_accounts_and_missing_names(edition):
    make_category(edition, "sur-place", label_fr="Sur place")
    client = client_for(make_member(edition, Role.OC_MEMBER, oc_function="secretariat"))
    path = f"/v1/manage/editions/{edition.pk}/registrations/counter"
    inactive = participant()
    User.objects.filter(pk=inactive.pk).update(is_active=False)
    response = client.post(path, {"email": inactive.email, "category": "sur-place"}, format="json")
    assert response.status_code == 400 and "email" in response.json()["fields"]
    response = client.post(path, {"email": "x@example.org", "category": "sur-place"}, format="json")
    assert response.status_code == 400
    assert set(response.json()["fields"]) == {"first_name", "last_name"}
    assert not User.objects.filter(email="x@example.org").exists()
