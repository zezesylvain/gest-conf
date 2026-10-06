"""Pointage à l'accueil (plan L7, K2, K4, K5 ; RG-16) : service."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.events.integrity import check_checkins
from apps.events.models import Checkin
from apps.events.services import checkin as service
from apps.events.services.checkin import Outcome
from apps.events.tests.helpers import confirmed, participant
from apps.registrations import workflow
from apps.registrations.models import RegistrationStatus, RetiredQrToken
from apps.registrations.services import orders
from apps.registrations.tests.factories import make_registration
from apps.registrations.tokens import token_hash

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def volunteer(edition):
    return Actor(kind=ActorKind.USER, user=make_member(edition, Role.VOLUNTEER))


def scan(edition, token, actor, **kwargs):
    return service.check_in(edition, token=token, actor=actor, **kwargs)


def test_rg16_scan_of_a_confirmed_badge_records_presence(edition, volunteer):
    registration = confirmed(edition)
    result = scan(edition, registration.qr_token, volunteer, device="Accueil 1")
    assert result.outcome == Outcome.CHECKED_IN
    checkin = Checkin.objects.get()
    assert (checkin.registration, checkin.session, checkin.method) == (registration, None, "scan")
    assert checkin.recorded_by == volunteer.user
    assert checkin.device == "Accueil 1"
    assert checkin.active_key == f"{registration.pk}:0"
    # Journal sans jeton.
    entry = AuditLog.objects.get(action="checkin.recorded")
    assert registration.qr_token not in str(entry.after)


def test_k4_second_scan_warns_without_new_row(edition, volunteer):
    registration = confirmed(edition)
    first = scan(edition, registration.qr_token, volunteer)
    second = scan(edition, registration.qr_token, volunteer)
    assert second.outcome == Outcome.ALREADY_CHECKED_IN
    assert second.checkin == first.checkin
    assert Checkin.objects.count() == 1


def test_k4_explicit_refusals(edition, volunteer):
    assert scan(edition, "jeton-inconnu-" + "x" * 20, volunteer).outcome == Outcome.UNKNOWN
    other = confirmed(EditionFactory())
    result = scan(edition, other.qr_token, volunteer)
    assert (result.outcome, result.registration) == (Outcome.OTHER_EDITION, None)
    # Badge d'une inscription annulée : son empreinte est gardée.
    cancelled = confirmed(edition)
    token = cancelled.qr_token
    workflow.transition(cancelled, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x")
    assert RetiredQrToken.objects.get(token_hash=token_hash(token)).reason == "cancelled"
    result = scan(edition, token, volunteer)
    assert (result.outcome, result.registration.pk) == (Outcome.CANCELLED, cancelled.pk)
    # Badge perdu puis remplacé : l'ancien est refusé, le nouveau accepté (K2).
    lost = confirmed(edition)
    old = lost.qr_token
    lost = orders.regenerate_qr_token(lost, reason="Badge perdu", actor=COMMAND)
    assert scan(edition, old, volunteer).outcome == Outcome.REPLACED
    assert scan(edition, lost.qr_token, volunteer).outcome == Outcome.CHECKED_IN
    assert Checkin.objects.count() == 1


def test_k4_manual_entry_by_reference_refuses_unpaid_and_closed_registrations(edition, volunteer):
    """Réponse du commanditaire : une inscription non payée est refusée à l'accueil."""
    pending = make_registration(edition, participant(), status=RegistrationStatus.PENDING)
    expired = make_registration(edition, participant(), status=RegistrationStatus.EXPIRED)
    ok = confirmed(edition)

    def manual(reference):
        return service.check_in(edition, reference=reference, method="manual", actor=volunteer)

    assert manual(pending.reference).outcome == Outcome.PENDING_PAYMENT
    assert manual(expired.reference).outcome == Outcome.EXPIRED
    assert manual("XX99-I00001").outcome == Outcome.UNKNOWN
    assert manual("n'importe quoi").outcome == Outcome.UNKNOWN
    assert manual(ok.reference.lower()).outcome == Outcome.CHECKED_IN
    assert Checkin.objects.get().method == "manual"


def test_k5_same_idempotency_key_replays_the_same_result(edition, volunteer):
    registration = confirmed(edition)
    first = scan(edition, registration.qr_token, volunteer, idempotency_key="appareil1-0001")
    again = scan(edition, registration.qr_token, volunteer, idempotency_key="appareil1-0001")
    assert first.outcome == again.outcome == Outcome.CHECKED_IN
    assert again.checkin == first.checkin
    assert Checkin.objects.count() == 1
    with pytest.raises(Invalid):
        scan(edition, registration.qr_token, volunteer, idempotency_key="court")
    # Clé d'une autre édition : refusée, sans fuite.
    other = EditionFactory()
    with pytest.raises(Invalid):
        scan(other, "x", volunteer, idempotency_key="appareil1-0001")


def test_k4_device_time_is_bounded(edition, volunteer):
    now = timezone.now()
    assert service.bounded_scan_time(now + dt.timedelta(hours=3), now) == now
    assert service.bounded_scan_time(now - dt.timedelta(days=3), now) == now - dt.timedelta(
        hours=24
    )
    earlier = now - dt.timedelta(minutes=40)
    assert service.bounded_scan_time(earlier, now) == earlier
    assert service.bounded_scan_time(None, now) == now


def test_k5_synchronization_rechecks_each_item(edition, volunteer):
    """Un pointage hors ligne d'une inscription annulée entre-temps est rejeté et signalé ;
    la saisie manuelle exige checkin.manage ; le lot est rejouable."""
    ok = confirmed(edition)
    cancelled = confirmed(edition)
    token = cancelled.qr_token
    workflow.transition(cancelled, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x")
    at = timezone.now() - dt.timedelta(minutes=30)
    items = [
        {"idempotency_key": "dev-0001", "method": "scan", "token": ok.qr_token, "scanned_at": at},
        {"idempotency_key": "dev-0002", "method": "scan", "token": token, "scanned_at": at},
        {"idempotency_key": "dev-0003", "method": "manual", "reference": ok.reference},
    ]
    results = service.synchronize(
        edition, items, device="Téléphone 2", may_enter_manually=False, actor=volunteer
    )
    assert [r.outcome for r in results] == [
        Outcome.CHECKED_IN,
        Outcome.CANCELLED,
        Outcome.NOT_ALLOWED,
    ]
    checkin = Checkin.objects.get()
    assert checkin.scanned_at == at and checkin.device == "Téléphone 2"
    replay = service.synchronize(
        edition, items[:2], device="Téléphone 2", may_enter_manually=False, actor=volunteer
    )
    assert [r.outcome for r in replay] == [Outcome.CHECKED_IN, Outcome.CANCELLED]
    assert Checkin.objects.count() == 1
    with pytest.raises(Invalid):
        service.synchronize(
            edition, items * 100, device="", may_enter_manually=True, actor=volunteer
        )


def test_k4_cancel_checkin_allows_a_new_one(edition, volunteer):
    registration = confirmed(edition)
    first = scan(edition, registration.qr_token, volunteer).checkin
    with pytest.raises(Invalid):
        service.cancel_checkin(first, reason=" ", actor=COMMAND)
    cancelled = service.cancel_checkin(first, reason="Erreur de badge", actor=COMMAND)
    assert cancelled.active_key is None and cancelled.cancel_reason == "Erreur de badge"
    with pytest.raises(RuleViolation):
        service.cancel_checkin(first, reason="Encore", actor=COMMAND)
    again = scan(edition, registration.qr_token, volunteer)
    assert again.outcome == Outcome.CHECKED_IN
    assert Checkin.objects.count() == 2
    assert AuditLog.objects.filter(action="checkin.cancelled").count() == 1


def test_archived_edition_refuses_checkins(edition, volunteer):
    registration = confirmed(edition)
    edition.status = EditionStatus.ARCHIVED
    edition.save()
    with pytest.raises(RuleViolation):
        scan(edition, registration.qr_token, volunteer)


def test_k5_offline_bundle_is_minimal_and_logged(edition, volunteer):
    """Ni jeton, ni adresse, ni institution : empreinte, référence, nom, catégorie."""
    registration = confirmed(edition)
    checked = confirmed(edition, participant("Kofi", "Mensah", institution="Institut secret"))
    scan(edition, checked.qr_token, volunteer)
    cancelled = confirmed(edition)
    token = cancelled.qr_token
    workflow.transition(cancelled, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x")
    make_registration(edition, participant(), status=RegistrationStatus.PENDING)
    bundle = service.offline_bundle(edition, actor=volunteer)
    entries = {entry["reference"]: entry for entry in bundle["entries"]}
    assert set(entries) == {registration.reference, checked.reference}
    assert entries[checked.reference] == {
        "token_hash": token_hash(checked.qr_token),
        "reference": checked.reference,
        "name": "Kofi Mensah",
        "category": checked.category.code,
        "checked_in": True,
    }
    assert entries[registration.reference]["checked_in"] is False
    assert bundle["retired"] == [
        {"token_hash": token_hash(token), "reference": cancelled.reference, "reason": "cancelled"}
    ]
    text = str(bundle)
    for secret in (registration.qr_token, checked.qr_token, "Institut secret", "@"):
        assert secret not in text
    assert bundle["expires_at"] - bundle["generated_at"] == dt.timedelta(hours=48)
    entry = AuditLog.objects.get(action="checkin.bundle_downloaded")
    assert entry.after == {"entries": 2, "retired": 1}


def test_summary_counts(edition, volunteer):
    first, second = confirmed(edition), confirmed(edition)
    make_registration(edition, participant(), status=RegistrationStatus.PENDING)
    scan(edition, first.qr_token, volunteer)
    assert service.summary(edition) == {"confirmed": 2, "pending": 1, "checked_in": 1}
    assert second  # pointée plus tard


def test_integrity_flags_checkins_of_cancelled_registrations(edition, volunteer):
    registration = confirmed(edition)
    scan(edition, registration.qr_token, volunteer)
    assert check_checkins() == []
    workflow.transition(registration, RegistrationStatus.CANCELLED, actor=COMMAND, reason="x")
    assert check_checkins() == [
        f"pointage {Checkin.objects.get().pk} : inscription {registration.pk} non confirmée"
    ]


def test_k2_regeneration_requires_a_confirmed_registration_and_a_reason(edition):
    pending = make_registration(edition, participant(), status=RegistrationStatus.PENDING)
    with pytest.raises(RuleViolation):
        orders.regenerate_qr_token(pending, reason="Perdu", actor=COMMAND)
    registration = confirmed(edition)
    with pytest.raises(Invalid):
        orders.regenerate_qr_token(registration, reason="", actor=COMMAND)
    old = registration.qr_token
    new = orders.regenerate_qr_token(registration, reason="Perdu", actor=COMMAND).qr_token
    assert new != old and len(new) == 32
    entry = AuditLog.objects.get(action="registration.qr_regenerated")
    assert old not in str(entry.after) and new not in str(entry.after)
    assert entry.reason == "Perdu"


@pytest.mark.mariadb_only  # SQLite verrouille la base entière : sans objet
@pytest.mark.django_db(transaction=True)
def test_k4_two_devices_scanning_the_same_badge_at_once():
    """Le verrou de l'inscription sérialise les deux lectures : un pointage, un « déjà
    pointé », jamais une erreur de contrainte."""
    import threading
    import time

    from django.db import connection as default_connection
    from django.db import transaction

    edition = EditionFactory()
    registration = confirmed(edition)
    actors = [Actor(kind=ActorKind.USER, user=make_member(edition, Role.VOLUNTEER)) for _ in "ab"]
    first_holds_lock = threading.Event()
    outcomes: list[str] = []

    def read(actor, *, hold: bool) -> None:
        try:
            with transaction.atomic():
                result = scan(edition, registration.qr_token, actor)
                outcomes.append(result.outcome)
                if hold:
                    first_holds_lock.set()
                    time.sleep(0.5)
        finally:
            default_connection.close()

    one = threading.Thread(target=read, args=(actors[0],), kwargs={"hold": True})
    one.start()
    assert first_holds_lock.wait(5)
    two = threading.Thread(target=read, args=(actors[1],), kwargs={"hold": False})
    two.start()
    one.join(10)
    two.join(10)
    assert sorted(outcomes) == [Outcome.ALREADY_CHECKED_IN, Outcome.CHECKED_IN]
    assert Checkin.objects.count() == 1
