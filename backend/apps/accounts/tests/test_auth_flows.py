"""Parcours d'authentification allauth headless (plan L1 §4.3, §12.2 « Parcours allauth »).

Critère de fin de L1.3 : inscription → vérification → connexion → profil → déconnexion,
e-mails uniquement via la file et dans la langue de la requête, anti-énumération,
CSRF, réauthentification exigée pour ajouter une adresse et notification de l'ajout.
"""

from unittest import mock

import pytest
from allauth.account.models import EmailAddress
from django.contrib.auth.hashers import MD5PasswordHasher
from django.core import mail
from django.test import Client

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, VerifiedUserFactory
from apps.accounts.tests.helpers import (
    AUTH,
    JSON,
    age_session,
    flow_ids,
    key_from_last_email,
    login,
    post,
    signup,
)
from apps.communications.models import OutboxEmail, OutboxStatus
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

VERIFY_MARKER = "/compte/verifier-email#"
RESET_MARKER = "/compte/reinitialiser#"


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    """Exécute les rappels « on_commit » (voie rapide des e-mails) à la fin du bloc."""
    return lambda: django_capture_on_commit_callbacks(execute=True)


def run_cron():
    import time

    from apps.core import jobs

    jobs.run_pending(deadline=time.monotonic() + 30)


# --- Parcours complet ---------------------------------------------------------------------


def test_signup_verify_login_profile_logout_journey(client, on_commit):
    """Critère de fin de L1.3, de bout en bout par le client HTTP."""
    with on_commit():
        response = signup(client, "awa.kone@univ.ci", HTTP_ACCEPT_LANGUAGE="en")
    assert response.status_code == 401
    assert "verify_email" in flow_ids(response)
    user = User.objects.get(email="awa.kone@univ.ci")
    assert user.locale == "en"

    # L'e-mail passe par la file (registre d'envoi), envoyé par la voie rapide.
    email = OutboxEmail.objects.get(to_email="awa.kone@univ.ci")
    assert email.template_code == "account/email/email_confirmation_signup"
    assert email.status == OutboxStatus.SENT
    assert email.locale == "en"
    assert mail.outbox[0].subject == "[GEST-CONF] Confirm your email address"
    # Corps à jeton purgé après l'envoi.
    assert email.body_text == ""

    key = key_from_last_email(VERIFY_MARKER)
    response = post(client, "auth/email/verify", {"key": key})
    assert response.status_code == 401  # vérifiée, mais pas de connexion automatique
    assert EmailAddress.objects.get(email="awa.kone@univ.ci").verified

    response = login(client, "awa.kone@univ.ci")
    assert response.status_code == 200
    assert response.json()["meta"]["is_authenticated"] is True

    me = client.get("/v1/me")
    assert me.status_code == 200
    assert me.json()["email"] == "awa.kone@univ.ci"
    assert me.json()["locale"] == "en"

    response = client.patch(
        "/v1/me/profile",
        {"first_name": "Awa", "last_name": "Koné", "institution": "UFHB", "country": "ci"},
        content_type=JSON,
    )
    assert response.status_code == 200
    assert response.json()["is_complete"] is True
    assert client.get("/v1/me").json()["profile_complete"] is True

    cookie = client.cookies["sessionid"].value
    response = client.delete(f"{AUTH}/auth/session")
    assert response.status_code == 401
    assert client.get("/v1/me").status_code == 401

    # L'ancien cookie de session est refusé après la déconnexion.
    replay = Client()
    replay.cookies["sessionid"] = cookie
    assert replay.get("/v1/me").status_code == 401

    actions = list(AuditLog.objects.order_by("id").values_list("action", flat=True))
    for expected in (
        "account.signed_up",
        "account.email_confirmed",
        "auth.login",
        "profile.updated",
        "auth.logout",
    ):
        assert expected in actions


def test_unverified_account_cannot_log_in_and_relogin_resends_link(client, on_commit):
    with on_commit():
        signup(client, "moussa@univ.ci")
    sent = len(mail.outbox)
    fresh = Client()
    response = login(fresh, "moussa@univ.ci")
    assert response.status_code == 401
    assert "verify_email" in flow_ids(response)
    # Renvoi au plus une fois toutes les 180 s par adresse (limite confirm_email d'allauth).
    assert len(mail.outbox) == sent


def test_session_key_is_renewed_at_login(client):
    user = VerifiedUserFactory()
    client.get(f"{AUTH}/auth/session")
    before = client.session.session_key
    assert login(client, user.email).status_code == 200
    assert client.session.session_key != before


def test_too_many_failed_logins_are_throttled(client):
    user = VerifiedUserFactory()
    codes = [login(client, user.email, "mauvais-mot-de-passe").status_code for _ in range(6)]
    assert codes[:5] == [400] * 5
    response = login(client, user.email, "mauvais-mot-de-passe")
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "too_many_login_attempts"


def test_failed_login_is_audited_without_clear_email(client):
    user = VerifiedUserFactory()
    login(client, user.email, "mauvais-mot-de-passe")
    login(client, "inconnu@example.org", "mauvais-mot-de-passe")
    known, unknown = AuditLog.objects.filter(action="auth.login_failed").order_by("id")
    assert (known.object_type, known.object_id) == ("accounts.user", str(user.pk))
    assert unknown.object_id == ""
    assert unknown.ip == "127.0.0.1"


# --- Langue des e-mails ----------------------------------------------------------------------


def test_signup_with_accept_language_en_sends_english_verification(client, on_commit):
    with on_commit():
        signup(client, "en@example.org", HTTP_ACCEPT_LANGUAGE="en-GB,en;q=0.9")
    assert mail.outbox[0].subject == "[GEST-CONF] Confirm your email address"
    assert "confirm your address" in mail.outbox[0].body


def test_signup_defaults_to_french(client, on_commit):
    with on_commit():
        signup(client, "fr@example.org", HTTP_ACCEPT_LANGUAGE="de")
    assert User.objects.get(email="fr@example.org").locale == "fr"
    assert mail.outbox[0].subject == "[GEST-CONF] Confirmez votre adresse e-mail"


# --- Anti-énumération (§4.11) ---------------------------------------------------------------


def _count_signup_side_effects(client, on_commit, email):
    with (
        mock.patch.object(
            MD5PasswordHasher, "encode", autospec=True, side_effect=MD5PasswordHasher.encode
        ) as encode,
        on_commit(),
    ):
        response = signup(client, email)
    return response, encode.call_count, len(mail.outbox)


def test_no_timing_oracle_on_signup(on_commit):
    """Adresse nouvelle ou existante : réponse identique, même nombre de hachages de mot de
    passe et même nombre d'envois pendant la requête (§4.11)."""
    existing = VerifiedUserFactory()
    new_response, new_hashes, new_sent = _count_signup_side_effects(
        Client(), on_commit, "nouvelle@example.org"
    )
    mail.outbox.clear()
    old_response, old_hashes, old_sent = _count_signup_side_effects(
        Client(), on_commit, existing.email
    )
    assert new_response.status_code == old_response.status_code == 401
    assert new_response.json() == old_response.json()
    assert new_hashes == old_hashes == 1
    assert new_sent == old_sent == 1
    assert mail.outbox[0].subject == "[GEST-CONF] Un compte existe déjà avec cette adresse"


def test_no_timing_oracle_on_password_request(on_commit):
    """Compte connu ou inconnu : réponse identique, aucun envoi pendant la requête,
    aucun hachage ; l'e-mail du compte connu attend le cron."""
    user = VerifiedUserFactory()
    responses = []
    for email in (user.email, "personne@example.org"):
        with (
            mock.patch.object(
                MD5PasswordHasher, "encode", autospec=True, side_effect=MD5PasswordHasher.encode
            ) as encode,
            on_commit(),
        ):
            responses.append(post(Client(), "auth/password/request", {"email": email}))
        assert encode.call_count == 0
        assert mail.outbox == []
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    # Rien pour l'adresse inconnue (EMAIL_UNKNOWN_ACCOUNTS=False) ; le cron envoie l'autre.
    run_cron()
    assert [message.to for message in mail.outbox] == [[user.email]]


def test_password_reset_link_is_single_use(client):
    user = VerifiedUserFactory()
    post(client, "auth/password/request", {"email": user.email})
    run_cron()
    key = key_from_last_email(RESET_MARKER)
    response = client.get(f"{AUTH}/auth/password/reset", HTTP_X_PASSWORD_RESET_KEY=key)
    assert response.status_code == 200
    assert post(client, "auth/password/reset", {"key": key, "password": "nouveau-mot-de-passe-1"})
    response = post(client, "auth/password/reset", {"key": key, "password": "encore-un-autre-1"})
    assert response.status_code == 400
    assert response.json()["errors"][0]["code"] == "invalid_password_reset"
    user.refresh_from_db()
    assert user.check_password("nouveau-mot-de-passe-1")
    assert AuditLog.objects.filter(action="auth.password_reset", object_id=str(user.pk)).exists()


def test_password_reset_not_sent_to_unverified_secondary_address(client):
    """Plan v3 : une adresse ajoutée mais jamais vérifiée ne reçoit pas de lien de
    réinitialisation ; une adresse secondaire vérifiée, si."""
    user = VerifiedUserFactory()
    EmailAddress.objects.create(user=user, email="pirate@example.org", verified=False)
    EmailAddress.objects.create(user=user, email="pro@example.org", verified=True)
    for email in ("pirate@example.org", "pro@example.org"):
        assert post(Client(), "auth/password/request", {"email": email}).status_code == 200
    run_cron()
    assert [message.to for message in mail.outbox] == [["pro@example.org"]]


def test_reset_links_use_public_url_despite_forged_host(client, settings):
    settings.ALLOWED_HOSTS = ["testserver", "pirate.example"]
    user = VerifiedUserFactory()
    post(client, "auth/password/request", {"email": user.email}, HTTP_HOST="pirate.example")
    run_cron()
    body = mail.outbox[-1].body
    assert "pirate.example" not in body
    assert f"{settings.GESTCONF_PUBLIC_URL}/compte/reinitialiser#" in body


# --- Gestion des adresses : réauthentification et notification ------------------------------


def test_add_email_requires_recent_reauth(client):
    """Plan v3 : sans réauthentification récente, 401 avec le flux « reauthenticate » et
    aucune adresse ajoutée."""
    user = VerifiedUserFactory()
    login(client, user.email)
    age_session(client, auth_seconds_ago=301)
    response = post(client, "account/email", {"email": "seconde@example.org"})
    assert response.status_code == 401
    assert "reauthenticate" in flow_ids(response)
    assert not EmailAddress.objects.filter(email="seconde@example.org").exists()

    assert post(client, "auth/reauthenticate", {"password": DEFAULT_PASSWORD}).status_code == 200
    response = post(client, "account/email", {"email": "seconde@example.org"})
    assert response.status_code == 200


def test_email_added_notifies_primary(client, on_commit):
    user = VerifiedUserFactory()
    login(client, user.email)
    with on_commit():
        post(client, "account/email", {"email": "seconde@example.org"})
    notification = OutboxEmail.objects.get(template_code="account/email/email_added")
    assert notification.to_email == user.email
    assert notification.to_user == user
    # L'adresse ajoutée figure dans le corps, jamais dans l'objet.
    message = next(m for m in mail.outbox if m.to == [user.email])
    assert "seconde@example.org" in message.body
    assert "seconde@example.org" not in message.subject
    # La nouvelle adresse reçoit son lien de vérification.
    assert any(m.to == ["seconde@example.org"] for m in mail.outbox)
    entry = AuditLog.objects.get(action="account.email_added")
    assert entry.after == {"email_masked": "s***@example.org"}


def test_password_change_invalidates_other_sessions(client):
    user = VerifiedUserFactory()
    other = Client()
    login(client, user.email)
    login(other, user.email)
    response = post(
        client,
        "account/password/change",
        {"current_password": DEFAULT_PASSWORD, "new_password": "un-autre-mot-de-passe-1"},
    )
    assert response.status_code == 200
    assert client.get("/v1/me").status_code == 200
    assert other.get("/v1/me").status_code == 401
    assert OutboxEmail.objects.filter(template_code="account/email/password_changed").exists()


# --- CSRF et routes neutralisées ---------------------------------------------------------------


def test_allauth_csrf_failure_is_json(csrf_api_client):
    """§4.6, cas 1 : vues allauth protégées par le middleware CSRF → CSRF_FAILURE_VIEW."""
    response = csrf_api_client.post(
        f"{AUTH}/auth/login", {"email": "a@b.org", "password": "x"}, format="json"
    )
    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_session_bootstrap_sets_csrf_cookie(client):
    response = client.get(f"{AUTH}/auth/session")
    assert response.status_code == 401
    assert "csrftoken" in response.cookies


@pytest.mark.parametrize(
    "path",
    ["/_allauth/app/v1/config", f"{AUTH}/auth/2fa/trust", f"{AUTH}/auth/code/request"],
)
def test_unconfigured_routes_are_absent(client, path):
    """Client « app » désactivé ; confiance d'appareil et connexion par code non routées."""
    assert client.post(path, content_type=JSON).status_code in (404, 409)


def test_resend_verification_endpoint_is_inert_in_link_mode(client):
    assert post(client, "auth/email/verify/resend").status_code == 409


@pytest.mark.parametrize(
    "route", ["account/phone", "auth/phone/verify", "auth/phone/verify/resend"]
)
def test_phone_routes_are_disabled(client, route):
    """Sans adaptateur de téléphone, allauth lèverait NotImplementedError (500) :
    les routes sont neutralisées (config/urls.py) et répondent 404 JSON."""
    user = VerifiedUserFactory()
    login(client, user.email)
    for response in (
        client.get(f"{AUTH}/{route}"),
        post(client, route, {"phone": "+2250102030405"}),
    ):
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"
