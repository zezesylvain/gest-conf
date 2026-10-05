"""Acteur d'une opération métier (plan L1 §1.4, §7.2)."""

import dataclasses

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, override_settings

from apps.core.actor import Actor, ActorKind


def make_request(user=None, **meta):
    request = RequestFactory().get("/", **meta)
    request.user = user if user is not None else AnonymousUser()
    request.request_id = "0123456789abcdef0123456789abcdef"
    return request


@pytest.mark.django_db
def test_from_request_authenticated_user(user):
    request = make_request(user, REMOTE_ADDR="203.0.113.9", HTTP_USER_AGENT="Navigateur/1.0")
    actor = Actor.from_request(request)
    assert actor.kind == ActorKind.USER
    assert actor.user == user
    assert actor.label == ""
    assert actor.ip == "203.0.113.9"
    assert actor.user_agent == "Navigateur/1.0"
    assert actor.request_id == "0123456789abcdef0123456789abcdef"


def test_from_request_anonymous_visitor():
    actor = Actor.from_request(make_request(REMOTE_ADDR="203.0.113.9"))
    assert actor.kind == ActorKind.USER
    assert actor.user is None


@override_settings(GESTCONF_TRUSTED_PROXY_COUNT=1)
def test_from_request_uses_client_ip():
    request = make_request(REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="198.51.100.7")
    assert Actor.from_request(request).ip == "198.51.100.7"


def test_from_request_truncates_user_agent():
    actor = Actor.from_request(make_request(HTTP_USER_AGENT="x" * 1000))
    assert len(actor.user_agent) == 255


def test_command_and_system():
    command = Actor.command("cli:operateur")
    assert (command.kind, command.user, command.label) == (ActorKind.COMMAND, None, "cli:operateur")
    job = Actor.system("job:email.send")
    assert (job.kind, job.user, job.label) == (ActorKind.SYSTEM, None, "job:email.send")


@pytest.mark.parametrize("label", ["", "x" * 65])
def test_command_label_is_required_and_bounded(label):
    with pytest.raises(ValueError, match="Libellé"):
        Actor.command(label)


@pytest.mark.django_db
def test_command_cannot_carry_a_user(user):
    with pytest.raises(ValueError, match="utilisateur"):
        Actor(kind=ActorKind.COMMAND, user=user, label="cli:operateur")


def test_user_actor_has_no_label():
    with pytest.raises(ValueError, match="libellé"):
        Actor(kind=ActorKind.USER, label="cli:operateur")


def test_actor_is_immutable():
    actor = Actor.system("job:test")
    with pytest.raises(dataclasses.FrozenInstanceError):
        actor.label = "autre"  # type: ignore[misc]
