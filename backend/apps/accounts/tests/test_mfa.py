"""Double authentification (plan L1 §4.4, §4.10, §10.2, §12.2 « 2FA (L1.6) » ; D2, D3)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

import pytest
from allauth.mfa.models import Authenticator
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import Client, override_settings

from apps.accounts.adapters import MFAAdapter
from apps.accounts.models import Role
from apps.accounts.services.mfa import PENDING_TOTP_SECRET_SESSION_KEY, rotate_mfa_keys
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.helpers import AUTH, flow_ids, login, post
from apps.accounts.tests.roles_helpers import (
    TEST_TOTP_SECRET,
    client_for,
    enable_totp,
    make_member,
)
from apps.communications.models import OutboxEmail
from apps.conferences.tests.factories import EditionFactory
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

OTHER_KEY = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
TEST_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def totp_code(secret: str, *, offset: int = 0) -> str:
    """Code TOTP RFC 6238 (SHA-1, 6 chiffres, 30 s), calculé indépendamment d'allauth."""
    counter = int(time.time()) // 30 + offset
    digest = hmac.new(
        base64.b32decode(secret, casefold=True), struct.pack(">Q", counter), hashlib.sha1
    ).digest()
    start = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[start : start + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def manage_url(edition) -> str:
    return f"/v1/manage/editions/{edition.pk}"


# --- MfaVerified (§4.4) ---------------------------------------------------------------------


def test_chair_without_mfa_gets_enrollment_required():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.CHAIR), mfa=False)
    response = client.get(manage_url(edition))
    assert response.status_code == 403
    assert response.json()["code"] == "mfa_enrollment_required"


def test_enrolled_chair_without_mfa_session_gets_mfa_required_then_200():
    """§13, critère de L1.6 : ``mfa_enrollment_required`` → ``mfa_required`` → 200."""
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    client = client_for(chair, mfa=False)
    assert client.get(manage_url(edition)).json()["code"] == "mfa_enrollment_required"
    enable_totp(chair)
    response = client.get(manage_url(edition))
    assert (response.status_code, response.json()["code"]) == (403, "mfa_required")
    reauth = post(client, "auth/2fa/reauthenticate", {"code": totp_code(TEST_TOTP_SECRET)})
    assert reauth.status_code == 200, reauth.json()
    assert client.get(manage_url(edition)).status_code == 200
    me = client.get("/v1/me").json()
    assert (me["mfa_enabled"], me["mfa_verified"]) == (True, True)


def test_login_with_two_steps_gives_mfa_session():
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    enable_totp(chair)
    client = Client()
    response = login(client, chair.email)
    assert response.status_code == 401
    assert "mfa_authenticate" in flow_ids(response)
    response = post(client, "auth/2fa/authenticate", {"code": totp_code(TEST_TOTP_SECRET)})
    assert response.status_code == 200
    assert client.get(manage_url(edition)).status_code == 200


def test_reviewer_and_author_not_concerned():
    """D3 : ``SC_MEMBER`` et ``AUTHOR`` ne sont pas soumis à la 2FA (refus ordinaire, sans
    code ``mfa_*``) ; la liste des éditions du sélecteur ne l'exige pas non plus."""
    edition = EditionFactory()
    for role in (Role.SC_MEMBER, Role.AUTHOR):
        client = client_for(make_member(edition, role), mfa=False)
        response = client.get(manage_url(edition))
        assert response.status_code == 403
        assert response.json()["code"] == "permission_denied"
    chair_client = client_for(make_member(edition, Role.CHAIR), mfa=False)
    assert chair_client.get("/v1/manage/editions").status_code == 200


def test_capability_checked_before_mfa():
    """Ordre 401 → 404 → 403 capacité → 403 ``mfa_*`` : un ``OC_MEMBER`` (2FA imposée) sans
    la capacité d'écriture reçoit ``permission_denied``, pas une invitation à la 2FA."""
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.OC_MEMBER), mfa=False)
    response = client.patch(manage_url(edition), {"venue": "Palais"})
    assert response.json()["code"] == "permission_denied"
    assert client.get(manage_url(edition)).json()["code"] == "mfa_enrollment_required"


def test_deleting_totp_requires_reenrollment():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.CHAIR))
    assert client.get(manage_url(edition)).status_code == 200
    response = client.delete(f"{AUTH}/account/authenticators/totp")
    assert response.status_code == 200, response.json()
    assert client.get(manage_url(edition)).json()["code"] == "mfa_enrollment_required"
    assert AuditLog.objects.filter(action="mfa.disabled").exists()
    assert OutboxEmail.objects.filter(template_code="mfa/email/totp_deactivated").exists()


# --- Enrôlement (§4.3, §10.2) ---------------------------------------------------------------


def test_enrollment_with_qr_code_encryption_and_notification(
    django_capture_on_commit_callbacks,
):
    user = VerifiedUserFactory()
    client = client_for(user, mfa=False)
    assert client.get("/v1/me/totp-qr").status_code == 404
    pending = client.get(f"{AUTH}/account/authenticators/totp")
    assert pending.status_code == 404
    secret = pending.json()["meta"]["secret"]
    qr = client.get("/v1/me/totp-qr")
    assert qr.status_code == 200
    assert qr["Cache-Control"] == "no-store"
    assert qr.json()["qr_code"].startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(qr.json()["qr_code"].split(",", 1)[1]).decode()
    assert svg.lstrip().startswith("<?xml") or "<svg" in svg
    # allauth émet le signal et la notification après la validation de la transaction.
    with django_capture_on_commit_callbacks(execute=True):
        response = post(client, "account/authenticators/totp", {"code": totp_code(secret)})
    assert response.status_code == 200, response.json()
    # Le secret en attente quitte la session ; il est chiffré en base.
    assert client.get("/v1/me/totp-qr").status_code == 404
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM mfa_authenticator WHERE type = 'totp'")
        raw = cursor.fetchone()[0]
    assert secret not in raw
    assert AuditLog.objects.filter(action="mfa.enabled", object_id=str(user.pk)).exists()
    assert OutboxEmail.objects.filter(template_code="mfa/email/totp_activated").exists()
    # L'activation n'inscrit pas « mfa » dans la session (constaté, §4.3).
    assert client.get("/v1/me").json()["mfa_verified"] is False


def test_totp_issuer_is_fixed_not_host(settings):
    user = VerifiedUserFactory(email="awa@example.org")
    url = MFAAdapter().build_totp_url(user, TEST_TOTP_SECRET)
    assert "issuer=GEST-CONF" in url


def test_activation_refused_with_unverified_address():
    from allauth.account.models import EmailAddress

    user = VerifiedUserFactory()
    EmailAddress.objects.create(user=user, email="autre@example.org", verified=False)
    client = client_for(user, mfa=False)
    # Refus dès la demande du secret : 409, code d'erreur « unverified_email ».
    response = client.get(f"{AUTH}/account/authenticators/totp")
    assert response.status_code == 409
    assert response.json()["errors"][0]["code"] == "unverified_email"
    response = post(client, "account/authenticators/totp", {"code": "123456"})
    assert response.status_code in (400, 409)
    assert not Authenticator.objects.filter(user=user).exists()


def test_same_code_cannot_be_replayed():
    user = VerifiedUserFactory()
    client = client_for(user, mfa=False)
    enable_totp(user)
    code = totp_code(TEST_TOTP_SECRET)
    assert post(client, "auth/2fa/reauthenticate", {"code": code}).status_code == 200
    replay = post(client, "auth/2fa/reauthenticate", {"code": code})
    assert replay.status_code == 400
    assert AuditLog.objects.filter(action="mfa.failed").exists()


# --- Chiffrement et rotation (§4.10) ------------------------------------------------------


def test_adapter_round_trip_and_raw_value_is_encrypted():
    adapter = MFAAdapter()
    encrypted = adapter.encrypt(TEST_TOTP_SECRET)
    assert TEST_TOTP_SECRET not in encrypted
    assert adapter.decrypt(encrypted) == TEST_TOTP_SECRET


def test_rotate_mfa_keys():
    user = VerifiedUserFactory()
    enable_totp(user)
    with override_settings(GESTCONF_MFA_ENCRYPTION_KEYS=[OTHER_KEY, TEST_KEY]):
        assert rotate_mfa_keys() == 1
    # Ancienne clé retirée : le secret reste lisible avec la nouvelle seule.
    with override_settings(GESTCONF_MFA_ENCRYPTION_KEYS=[OTHER_KEY]):
        authenticator = Authenticator.objects.get(user=user)
        assert MFAAdapter().decrypt(authenticator.data["secret"]) == TEST_TOTP_SECRET
        call_command("rotate_mfa_keys", "--dry-run")
    assert AuditLog.objects.filter(action="mfa.keys_rotated").count() == 0


def test_rotate_command_is_audited():
    enable_totp(VerifiedUserFactory())
    call_command("rotate_mfa_keys")
    assert AuditLog.objects.get(action="mfa.keys_rotated").after == {"count": 1}


# --- reset_mfa (§4.3, §9.4) ------------------------------------------------------------------


def test_reset_mfa_command():
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    client = client_for(chair)
    assert client.get(manage_url(edition)).status_code == 200
    call_command("reset_mfa", "--email", chair.email, "--reason", "Téléphone perdu")
    assert not Authenticator.objects.filter(user=chair).exists()
    entry = AuditLog.objects.get(action="mfa.reset")
    assert (entry.actor_kind, entry.reason) == ("command", "Téléphone perdu")
    assert entry.before == {"types": ["totp"]}
    assert OutboxEmail.objects.filter(template_code="mfa/email/mfa_reset").exists()
    assert client.get(manage_url(edition)).json()["code"] == "mfa_enrollment_required"


def test_reset_mfa_requires_known_account_and_reason():
    with pytest.raises(CommandError):
        call_command("reset_mfa", "--email", "absent@example.org", "--reason", "x")
    user = VerifiedUserFactory()
    with pytest.raises(CommandError):
        call_command("reset_mfa", "--email", user.email, "--reason", " ")


# --- Contrat d'allauth (§4.5) --------------------------------------------------------------


def test_pending_secret_session_key_contract():
    """Clé interne lue par ``/v1/me/totp-qr`` : doit rester celle d'allauth."""
    from allauth.mfa.totp.internal.auth import SECRET_SESSION_KEY

    assert SECRET_SESSION_KEY == PENDING_TOTP_SECRET_SESSION_KEY


def test_mfa_authentication_record_contract():
    """``session_has_mfa`` lit l'entrée ``method == "mfa"`` écrite par allauth."""
    user = VerifiedUserFactory()
    client = client_for(user, mfa=False)
    enable_totp(user)
    post(client, "auth/2fa/reauthenticate", {"code": totp_code(TEST_TOTP_SECRET)})
    records = client.session["account_authentication_methods"]
    assert records[-1]["method"] == "mfa"
    assert isinstance(records[-1]["at"], float)
