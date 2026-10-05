"""Commandes de l'opérateur : sync_email_addresses, deactivate_user, audit_query (§9.4)."""

from io import StringIO

import pytest
from allauth.account.models import EmailAddress
from django.core.management import CommandError, call_command
from django.test import Client

from apps.accounts.tests.factories import UserFactory, VerifiedUserFactory
from apps.accounts.tests.helpers import login
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db


def run(name, *args, **options):
    out = StringIO()
    call_command(name, *args, stdout=out, **options)
    return out.getvalue()


def test_sync_email_addresses_creates_missing_primary_addresses():
    """Comptes L0 sans EmailAddress : sans elle, la connexion répond 401 verify_email
    (allauth crée alors une adresse non vérifiée et envoie un lien)."""
    legacy = UserFactory()
    VerifiedUserFactory()
    assert "1 adresse(s) à créer" in run("sync_email_addresses", dry_run=True)
    assert not EmailAddress.objects.filter(user=legacy).exists()
    run("sync_email_addresses", verified=True)
    address = EmailAddress.objects.get(user=legacy)
    assert (address.email, address.primary, address.verified) == (legacy.email, True, True)
    assert login(Client(), legacy.email).status_code == 200
    assert "0 adresse(s)" in run("sync_email_addresses", verified=True)
    assert AuditLog.objects.filter(action="command.sync_email_addresses").count() == 2


def test_deactivate_user_closes_sessions_and_requires_reason():
    user = VerifiedUserFactory()
    client = Client()
    login(client, user.email)
    with pytest.raises(CommandError):
        run("deactivate_user", email=user.email, reason="  ")
    output = run("deactivate_user", email=user.email, reason="demande écrite du 5/10")
    assert "1 session(s) fermée(s)" in output
    assert client.get("/v1/me").status_code == 401
    assert login(Client(), user.email).status_code == 401
    entry = AuditLog.objects.get(action="account.deactivated")
    assert entry.reason == "demande écrite du 5/10"
    assert entry.actor_label.startswith("cli:")


def test_deactivate_unknown_user():
    with pytest.raises(CommandError):
        run("deactivate_user", email="personne@example.org", reason="x")


def test_audit_query_filters_and_is_itself_audited():
    user = VerifiedUserFactory()
    login(Client(), user.email)
    login(Client(), "inconnu@example.org", "mauvais-mot-de-passe")
    output = run("audit_query", action="auth.", email=user.email)
    assert "auth.login" in output
    assert "ip=127.0.0.1" in output
    assert "auth.login_failed" not in output  # l'échec visait un autre compte
    entry = AuditLog.objects.get(action="audit.queried")
    assert entry.after["filters"]["action"] == "auth."
    assert "@" not in entry.after["filters"]["email"].split("***")[0]


def test_audit_query_rejects_bad_date():
    with pytest.raises(CommandError):
        run("audit_query", since="05/10/2026")
