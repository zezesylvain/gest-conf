"""RG-17 : balayage de toutes les actions journalisées (plan L1 §7.5, v4).

Chaque action du catalogue ``AuditAction`` est produite par son vrai chemin de code
(commande, méthode nommée, purge), avec des adresses en clair partout où elles peuvent
entrer ; puis toutes les valeurs de ``before`` et ``after`` sont parcourues récursivement.
Une action ajoutée au catalogue sans fabrique ici fait échouer le test de complétude.
"""

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.core.actor import Actor
from apps.core.audit import FORBIDDEN_KEYS, AuditAction, contains_clear_email
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

CLEAR_ADDRESS = "jean.dupont@univ.ci"


def _send_test_email(user):
    call_command("send_test_email", "--to", CLEAR_ADDRESS, stdout=io.StringIO())


def _outbox_retry(user):
    call_command("send_test_email", "--to", CLEAR_ADDRESS, stdout=io.StringIO())
    email = OutboxEmail.objects.latest("pk")
    OutboxEmail.objects.filter(pk=email.pk).update(status=OutboxStatus.FAILED)
    call_command(
        "outbox",
        "--retry",
        str(email.pk),
        "--reason",
        f"demande de {CLEAR_ADDRESS}",
        stdout=io.StringIO(),
    )


def _user_actor(user):
    request = RequestFactory().get("/", REMOTE_ADDR="203.0.113.5")
    request.user = user
    request.request_id = "a" * 32
    return Actor.from_request(request)


def _audit_network_purge(user):
    AuditLog.objects.purge_network_before(timezone.now(), actor=Actor.system("job:cleanup"))


def _audit_purge(user):
    AuditLog.objects.purge_before(
        timezone.now() - timedelta(days=1), actor=Actor.system("job:cleanup")
    )


def _audit_redact(user):
    AuditLog.objects.redact_network_for_user(user, actor=_user_actor(user))


def _retention_applied(user):
    with override_settings(GESTCONF_RETENTION_ENFORCE=True):
        call_command("cleanup", stdout=io.StringIO())


FACTORIES = {
    AuditAction.COMMAND_SEND_TEST_EMAIL: _send_test_email,
    AuditAction.COMMAND_OUTBOX_RETRY: _outbox_retry,
    AuditAction.AUDIT_NETWORK_PURGED: _audit_network_purge,
    AuditAction.AUDIT_PURGED: _audit_purge,
    AuditAction.AUDIT_NETWORK_REDACTED: _audit_redact,
    AuditAction.RETENTION_APPLIED: _retention_applied,
}


def test_every_action_has_a_factory():
    """Complétude : toute nouvelle action du catalogue doit être balayée ci-dessous."""
    assert set(FACTORIES) == set(AuditAction)


def _keys(value):
    if isinstance(value, dict):
        found = set(value)
        for item in value.values():
            found |= _keys(item)
        return found
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


def test_rg17_no_clear_email_in_any_audit_state(user):
    """RG-17 : aucune adresse en clair dans before/after, pour toutes les actions (§7.5)."""
    for factory in FACTORIES.values():
        factory(user)
    entries = list(AuditLog.objects.all())
    assert {entry.action for entry in entries} == {action.value for action in AuditAction}
    for entry in entries:
        assert not contains_clear_email(entry.before), (entry.action, entry.before)
        assert not contains_clear_email(entry.after), (entry.action, entry.after)
        assert not _keys(entry.before) & FORBIDDEN_KEYS
        assert not _keys(entry.after) & FORBIDDEN_KEYS
        assert CLEAR_ADDRESS not in entry.actor_label
