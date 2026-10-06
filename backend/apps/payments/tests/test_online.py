"""Paiement en ligne (plan L6, J6) et RG-15 : une inscription n'est confirmée que par une
notification au jeton valide **et** un statut interrogé côté serveur ; le retour du
navigateur et le contenu d'une notification ne prouvent rien."""

from __future__ import annotations

import datetime as dt

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.roles_helpers import client_for
from apps.conferences.models import Conference
from apps.core.actor import Actor
from apps.core.errors import ErrorCode, RuleViolation
from apps.core.models import AuditLog, Job
from apps.payments.models import BillingDocument, Payment, PaymentNotification
from apps.payments.providers import fake
from apps.payments.providers.base import ProviderError
from apps.payments.services import online
from apps.registrations.models import Registration
from apps.registrations.services import orders
from apps.registrations.services.settings import registration_settings
from apps.registrations.tests.helpers import complete_billing, grid, open_edition, participant_user

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:test")
WEBHOOK = "/v1/payments/webhook/fake"


@pytest.fixture(autouse=True)
def fake_provider(settings):
    settings.GESTCONF_PAYMENT_PROVIDER = "fake"
    settings.GESTCONF_PUBLIC_URL = "https://conference.test"


@pytest.fixture
def edition():
    edition = open_edition()
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    grid(edition, "etudiant", early_local="25000")
    complete_billing(edition)
    row = registration_settings(edition)
    row.online_enabled = True
    row.save()
    return edition


@pytest.fixture
def registration(edition):
    return orders.place_order(
        edition, participant_user(), category="etudiant", method="online", actor=COMMAND
    )


def notify(payment: Payment, *, token: str | None = None, client: APIClient | None = None):
    state = fake.get_state(payment.reference)
    body = {
        "merchant_transaction_id": payment.reference,
        "transaction_id": state["transaction_id"],
        "notify_token": token if token is not None else state["token"],
    }
    return (client or APIClient()).post(WEBHOOK, body, format="json")


def test_j6_start_online_payment_keeps_only_token_hash(registration):
    payment, url = online.start_online_payment(registration, actor=COMMAND)
    assert url == f"https://conference.test/api/v1/payments/fake/{payment.reference}"
    payment.refresh_from_db()
    assert payment.status == "pending" and payment.method == "online"
    token = fake.get_state(payment.reference)["token"]
    assert payment.notify_token_hash == online.token_hash(token)
    assert token not in str(Payment.objects.values().get(pk=payment.pk))


def test_j6_online_not_offered_without_provider_or_setting(registration, settings):
    settings.GESTCONF_PAYMENT_PROVIDER = ""
    with pytest.raises(RuleViolation) as error:
        online.start_online_payment(registration, actor=COMMAND)
    assert error.value.code == ErrorCode.PAYMENT_UNAVAILABLE


def test_rg15_browser_return_alone_confirms_nothing(registration):
    online.start_online_payment(registration, actor=COMMAND)
    # Le navigateur revient sur « Mon inscription » sans que le fournisseur ait réglé.
    assert online.check_latest(registration) == "pending"
    registration.refresh_from_db()
    assert registration.status == "pending"


def test_rg15_valid_notification_and_server_check_confirm_and_invoice(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")
    response = notify(payment)
    assert response.status_code == 200
    registration.refresh_from_db()
    assert registration.status == "confirmed" and registration.qr_token
    assert BillingDocument.objects.filter(registration=registration, kind="invoice").count() == 1
    note = PaymentNotification.objects.get()
    assert (note.token_valid, note.outcome) == (True, "confirmed")
    assert "notify_token" not in note.body


def test_rg15_invalid_token_has_no_effect(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")
    response = notify(payment, token="jeton-falsifie")
    assert response.status_code == 401
    registration.refresh_from_db()
    assert registration.status == "pending"
    note = PaymentNotification.objects.get()
    assert (note.token_valid, note.outcome) == (False, "invalid_token")


def test_rg15_replayed_notification_is_idempotent(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")
    notify(payment)
    notify(payment)
    assert AuditLog.objects.filter(action="registration.confirmed").count() == 1
    assert BillingDocument.objects.filter(kind="invoice").count() == 1
    assert list(PaymentNotification.objects.values_list("outcome", flat=True)) == [
        "confirmed",
        "confirmed",
    ]


def test_rg15_notification_does_not_override_failed_status(registration):
    """Le fournisseur dit « échoué » à l'interrogation : la notification ne confirme rien."""
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="FAILED")
    notify(payment)
    payment.refresh_from_db()
    registration.refresh_from_db()
    assert (payment.status, registration.status) == ("failed", "pending")


def test_rg15_amount_mismatch_is_not_confirmed(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS", amount="100")
    notify(payment)
    registration.refresh_from_db()
    assert registration.status == "pending"
    assert AuditLog.objects.filter(action="payment.mismatch").exists()


def test_provider_unreachable_defers_to_a_job(registration, monkeypatch):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")

    def down(self, payment):
        raise ProviderError("réseau")

    monkeypatch.setattr(fake.FakeProvider, "check", down)
    notify(payment)
    assert PaymentNotification.objects.get().outcome == "deferred"
    job = Job.objects.get(kind=online.RECONCILE_JOB)
    monkeypatch.undo()
    online.reconcile_job(job)
    registration.refresh_from_db()
    assert registration.status == "confirmed"


def test_payment_after_expiry_is_flagged_not_reconfirmed(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    Payment.objects.filter(pk=payment.pk).update(created_at=timezone.now() - dt.timedelta(hours=3))
    Registration.objects.filter(pk=registration.pk).update(
        due_at=timezone.now() - dt.timedelta(minutes=1)
    )
    assert orders.expire_overdue() == 1  # tentative ancienne, toujours en cours : expirée
    fake.set_state(payment.reference, status="SUCCESS")
    notify(payment)
    registration.refresh_from_db()
    assert registration.status == "expired"
    assert AuditLog.objects.filter(action="payment.orphan").exists()


def test_j5_expiry_postponed_while_a_recent_online_payment_is_pending(registration):
    online.start_online_payment(registration, actor=COMMAND)
    Registration.objects.filter(pk=registration.pk).update(
        due_at=timezone.now() - dt.timedelta(minutes=1)
    )
    assert orders.expire_overdue() == 0
    registration.refresh_from_db()
    assert registration.status == "pending"


def test_sync_payments_reconciles_and_abandons(registration):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")
    assert online.sync_payments()["checked"] == 0  # trop récent
    later = timezone.now() + dt.timedelta(minutes=11)
    assert online.sync_payments(later)["checked"] == 1
    registration.refresh_from_db()
    assert registration.status == "confirmed"


def test_sync_payments_abandons_old_pending_attempts(edition):
    stale = orders.place_order(
        edition, participant_user(), category="etudiant", method="online", actor=COMMAND
    )
    payment, _url = online.start_online_payment(stale, actor=COMMAND)
    counts = online.sync_payments(timezone.now() + dt.timedelta(days=8))
    payment.refresh_from_db()
    assert counts["abandoned"] == 1 and payment.status == "cancelled"


def test_webhook_accepts_form_and_ping_and_refuses_other_providers(registration, settings):
    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    fake.set_state(payment.reference, status="SUCCESS")
    state = fake.get_state(payment.reference)
    client = APIClient(enforce_csrf_checks=True)
    response = client.post(
        WEBHOOK,
        {"merchant_transaction_id": payment.reference, "notify_token": state["token"]},
        format="multipart",
    )
    assert response.status_code == 200
    assert client.get(WEBHOOK).status_code == 200
    assert client.post("/v1/payments/webhook/cinetpay", {}, format="json").status_code == 404
    assert client.post(WEBHOOK, {"x": "y"}, format="json").status_code == 400


def test_fake_checkout_page_pays_and_redirects(registration, settings):
    import re

    payment, _url = online.start_online_payment(registration, actor=COMMAND)
    browser = APIClient(enforce_csrf_checks=True)
    page = browser.get(f"/v1/payments/fake/{payment.reference}")
    assert page.status_code == 200 and b"Payer" in page.content
    url = f"/v1/payments/fake/{payment.reference}"
    # Sans jeton CSRF : refusé (la page factice est un formulaire de navigateur).
    assert browser.post(url, {"action": "pay"}, format="multipart").status_code == 403
    token = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', page.content).group(1)
    response = browser.post(
        url, {"action": "pay", "csrfmiddlewaretoken": token.decode()}, format="multipart"
    )
    assert response.status_code == 302
    assert response["Location"].endswith(f"/compte/mon-inscription?paiement={payment.reference}")
    registration.refresh_from_db()
    assert registration.status == "confirmed"
    settings.GESTCONF_PAYMENT_PROVIDER = "cinetpay"
    assert APIClient().get(f"/v1/payments/fake/{payment.reference}").status_code == 404


def test_participant_pay_and_check_endpoints(registration):
    client = client_for(registration.user)
    response = client.post(f"/v1/registrations/{registration.pk}/pay")
    assert response.status_code == 201
    reference = response.json()["reference"]
    assert response.json()["payment_url"].endswith(reference)
    check = client.post(f"/v1/registrations/{registration.pk}/payment-check").json()
    assert check == {"outcome": "pending", "status": "pending"}
    fake.set_state(reference, status="SUCCESS")
    check = client.post(f"/v1/registrations/{registration.pk}/payment-check").json()
    assert check == {"outcome": "confirmed", "status": "confirmed"}
    stranger = client_for(participant_user())
    assert stranger.post(f"/v1/registrations/{registration.pk}/pay").status_code == 404


def test_online_setting_requires_a_configured_provider(edition, settings):
    from apps.core.errors import Invalid
    from apps.registrations.services.settings import update_registration_settings

    settings.GESTCONF_PAYMENT_PROVIDER = ""
    row = registration_settings(edition)
    row.online_enabled = False
    row.save()
    with pytest.raises(Invalid) as error:
        update_registration_settings(edition, {"online_enabled": True}, actor=COMMAND)
    assert "online_enabled" in error.value.fields
