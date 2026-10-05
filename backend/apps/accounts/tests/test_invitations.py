"""Invitations aux rôles et RG-20 (plan L1 §5.7, §12.1 « Invitations »).

RG-20 : une invitation ne s'accepte que depuis un compte qui contrôle l'adresse invitée ;
le jeton seul ne suffit jamais.
"""

import datetime as dt
import time
from urllib.parse import unquote

import pytest
from allauth.account.models import EmailAddress
from django.core import mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import InvitationStatus, RoleInvitation, UserRole, UserRoleStatus
from apps.accounts.roles import Role
from apps.accounts.services import invitations as service
from apps.accounts.services.access import edition_access
from apps.accounts.tests.factories import VerifiedUserFactory
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.communications.models import OutboxEmail
from apps.conferences.tests.factories import EditionFactory
from apps.core import jobs
from apps.core.actor import Actor, ActorKind
from apps.core.errors import QuotaExceeded
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")


@pytest.fixture
def edition():
    return EditionFactory()


@pytest.fixture
def chair(edition):
    return make_member(edition, Role.CHAIR)


def invite(edition, inviter, email, role=Role.SC_MEMBER) -> str:
    """Crée une invitation par le service et renvoie le jeton (lu dans l'e-mail envoyé)."""
    actor = Actor(kind=ActorKind.USER, user=inviter)
    service.create_invitations(
        edition=edition,
        emails=[email],
        role=role,
        actor=actor,
        access=edition_access(inviter, edition.pk),
    )
    jobs.run_pending(deadline=time.monotonic() + 10)
    body = next(m.body for m in reversed(mail.outbox) if m.to == [email])
    return unquote(body.split("/compte/invitation#", 1)[1].split()[0])


def post(client, path, data):
    return client.post(f"/v1/invitations/{path}", data, format="json")


# --- Création ---------------------------------------------------------------------------


def test_invitation_token_never_stored_in_clear(edition, chair):
    token = invite(edition, chair, "relecteur@univ.ci")
    invitation = RoleInvitation.objects.get()
    assert token not in str(RoleInvitation.objects.values().get())
    assert invitation.token_hash == service.token_hash(token)
    assert len(invitation.pending_key) == 64
    # Corps de l'e-mail (lien à jeton) purgé après l'envoi.
    assert OutboxEmail.objects.get(template_code="role/email/invitation").body_text == ""


def test_rg17_invitation_snapshot_has_no_clear_email(edition, chair):
    invite(edition, chair, "jeanne.dupont@univ.ci")
    entry = AuditLog.objects.get(action="invitation.created")
    assert entry.after["email_masked"] == "j***@univ.ci"
    assert "jeanne.dupont" not in str(entry.after)
    assert entry.edition == edition


def test_invitation_single_pending_via_nullable_unique_key(edition, chair):
    invite(edition, chair, "a@univ.ci")
    batch = service.create_invitations(
        edition=edition,
        emails=["a@univ.ci"],
        role=Role.SC_MEMBER,
        actor=Actor(kind=ActorKind.USER, user=chair),
        access=edition_access(chair, edition.pk),
    )
    assert batch.created == []
    assert batch.skipped == [("a***@univ.ci", "already_pending")]
    assert RoleInvitation.objects.count() == 1


@pytest.mark.mariadb
def test_invitation_pending_key_fixed_length_with_254_char_email(edition, chair):
    """§3.1 : une adresse de 254 caractères ne tronque pas la clé et ne lève pas 1406."""
    local = "a" * 64
    domain = ".".join(["b" * 60, "c" * 60, "d" * 60, "e" * 63])[: 254 - 65]
    email = f"{local}@{domain}"
    assert len(email) == 254
    service.create_invitations(
        edition=edition,
        emails=[email],
        role=Role.SC_MEMBER,
        actor=Actor(kind=ActorKind.USER, user=chair),
        access=edition_access(chair, edition.pk),
    )
    invitation = RoleInvitation.objects.get()
    assert invitation.email == email
    with pytest.raises(IntegrityError), transaction.atomic():
        RoleInvitation.objects.create(
            edition=edition,
            email=email,
            role=Role.SC_MEMBER,
            token_hash="0" * 64,
            pending_key=invitation.pending_key,
            expires_at=timezone.now(),
            locale="fr",
            last_sent_at=timezone.now(),
        )


def test_invitation_expired_on_the_fly_unblocks_new_invitation(edition, chair):
    invite(edition, chair, "a@univ.ci")
    RoleInvitation.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    invite(edition, chair, "a@univ.ci")
    statuses = sorted(RoleInvitation.objects.values_list("status", flat=True))
    assert statuses == ["expired", "pending"]
    assert AuditLog.objects.filter(action="invitation.expired").count() == 1


def test_invitation_quota(edition, chair):
    """§4.7 : au-delà de 100 adresses par heure et par invitant → 429 avec Retry-After."""
    actor = Actor(kind=ActorKind.USER, user=chair)
    access = edition_access(chair, edition.pk)
    for batch in range(2):
        service.create_invitations(
            edition=edition,
            emails=[f"r{batch}-{n}@univ.ci" for n in range(50)],
            role=Role.SC_MEMBER,
            actor=actor,
            access=access,
        )
    with pytest.raises(QuotaExceeded):
        service.create_invitations(
            edition=edition,
            emails=["r101@univ.ci"],
            role=Role.SC_MEMBER,
            actor=actor,
            access=access,
        )
    response = client_for(chair).post(
        f"/v1/manage/editions/{edition.pk}/invitations",
        {"emails": ["r102@univ.ci"], "role": "SC_MEMBER"},
        format="json",
    )
    assert response.status_code == 429
    assert response.json()["code"] == "throttled"
    assert int(response["Retry-After"]) > 0


def test_fast_path_capped_per_request(edition, chair, django_capture_on_commit_callbacks):
    """§8.3 : 50 invitations en une requête → au plus 3 envois pendant la requête."""
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(chair).post(
            f"/v1/manage/editions/{edition.pk}/invitations",
            {"emails": [f"r{n}@univ.ci" for n in range(50)], "role": "SC_MEMBER"},
            format="json",
        )
    assert response.status_code == 201
    assert len(response.json()["created"]) == 50
    assert len(mail.outbox) == 3


def test_invitation_create_throttle_only_on_creation(edition, chair, settings):
    """§4.7 : la portée invitation_create ne compte que les créations, pas la liste."""
    client = client_for(chair)
    path = f"/v1/manage/editions/{edition.pk}/invitations"
    for _ in range(25):
        assert client.get(path).status_code == 200


def test_inviting_chair_requires_recent_reauth(edition):
    admin = make_member(edition, Role.ADMIN)
    response = client_for(admin, recent_auth=False).post(
        f"/v1/manage/editions/{edition.pk}/invitations",
        {"emails": ["chair@univ.ci"], "role": "CHAIR"},
        format="json",
    )
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"
    response = client_for(admin).post(
        f"/v1/manage/editions/{edition.pk}/invitations",
        {"emails": ["chair@univ.ci"], "role": "CHAIR"},
        format="json",
    )
    assert response.status_code == 201


# --- Consultation et refus (publics, CSRF imposé) ---------------------------------------


def test_lookup_masks_address_and_tells_if_controlled(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    body = post(APIClient(), "lookup", {"token": token}).json()
    assert body["email_masked"] == "a***@univ.ci"
    assert body["role"] == "SC_MEMBER"
    assert body["controls_address"] is False
    owner = VerifiedUserFactory(email="awa@univ.ci")
    assert post(client_for(owner), "lookup", {"token": token}).json()["controls_address"] is True
    assert post(APIClient(), "lookup", {"token": "inconnu"}).status_code == 404


def test_public_invitation_posts_enforce_csrf(edition, chair, csrf_api_client):
    token = invite(edition, chair, "awa@univ.ci")
    for path in ("lookup", "decline"):
        response = csrf_api_client.post(f"/v1/invitations/{path}", {"token": token}, format="json")
        assert response.status_code == 403
        assert response.json()["code"] == "csrf_failed"


def test_decline_without_account_and_new_invitation_possible(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    assert post(APIClient(), "decline", {"token": token}).status_code == 204
    assert RoleInvitation.objects.get().status == InvitationStatus.DECLINED
    assert AuditLog.objects.filter(action="invitation.declined").exists()
    invite(edition, chair, "awa@univ.ci")
    assert RoleInvitation.objects.filter(status=InvitationStatus.PENDING).count() == 1


# --- Acceptation (RG-20) -------------------------------------------------------------------


def test_rg20_accept_requires_verified_matching_email(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    owner = VerifiedUserFactory(email="awa@univ.ci")
    response = post(client_for(owner), "accept", {"token": token})
    assert response.status_code == 200
    assert response.json() == {"edition_id": edition.pk, "role": "SC_MEMBER"}
    user_role = UserRole.objects.get(user=owner)
    assert user_role.status == UserRoleStatus.ACTIVE
    assert user_role.granted_by == chair
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"role.granted", "invitation.accepted"} <= actions
    # Double acceptation refusée.
    second = post(client_for(owner), "accept", {"token": token})
    assert second.status_code == 409
    assert second.json()["code"] == "invitation_not_pending"


def test_rg20_bare_token_does_not_grant_role(edition, chair):
    """Le jeton seul ne suffit jamais : compte sans l'adresse → 409, aucun rôle."""
    token = invite(edition, chair, "awa@univ.ci")
    stranger = VerifiedUserFactory()
    response = post(client_for(stranger), "accept", {"token": token})
    assert response.status_code == 409
    assert response.json()["code"] == "invitation_email_unverified"
    assert not UserRole.objects.filter(user=stranger).exists()


def test_rg20_unverified_address_on_account_is_not_enough(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    user = VerifiedUserFactory()
    EmailAddress.objects.create(user=user, email="awa@univ.ci", verified=False)
    assert post(client_for(user), "accept", {"token": token}).json()["code"] == (
        "invitation_email_unverified"
    )


def test_rg20_address_verified_on_other_account_refused(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    VerifiedUserFactory(email="awa@univ.ci")
    other = VerifiedUserFactory()
    response = post(client_for(other), "accept", {"token": token})
    assert response.status_code == 409
    assert response.json()["code"] == "invitation_email_mismatch"


def test_inviter_cannot_accept_own_invitation(edition, chair):
    """Plan v3 : 403 ``invitation_self_accept`` ; aucune adresse liée, aucun rôle."""
    EmailAddress.objects.create(user=chair, email="moi.aussi@univ.ci", verified=True)
    token = invite(edition, chair, "moi.aussi@univ.ci")
    response = post(client_for(chair), "accept", {"token": token})
    assert response.status_code == 403
    assert response.json()["code"] == "invitation_self_accept"
    assert not UserRole.objects.filter(user=chair, role=Role.SC_MEMBER).exists()
    response = post(client_for(chair), "link-email", {"token": token})
    assert response.status_code == 403


def test_expired_invitation_refused(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    RoleInvitation.objects.update(expires_at=timezone.now() - dt.timedelta(seconds=1))
    owner = VerifiedUserFactory(email="awa@univ.ci")
    response = post(client_for(owner), "accept", {"token": token})
    assert response.json()["code"] == "invitation_expired"
    assert post(APIClient(), "lookup", {"token": token}).json()["status"] == "expired"


def test_accept_requires_authentication(edition, chair):
    token = invite(edition, chair, "awa@univ.ci")
    assert post(APIClient(), "accept", {"token": token}).status_code == 401


# --- Liaison d'adresse (RG-20 cas c, option (a) de D6) ---------------------------------


def _link_from_last_email(email: str) -> str:
    jobs.run_pending(deadline=time.monotonic() + 10)
    body = next(m.body for m in reversed(mail.outbox) if m.to == [email])
    return body.split("#lier=", 1)[1].split()[0]


def test_rg20_mfa_user_links_second_address_via_signed_link(edition, chair):
    """Un compte (2FA en L1.6) invité à une seconde adresse obtient le rôle par le lien de
    liaison ; l'adresse est ajoutée comme vérifiée et l'adresse principale prévenue."""
    token = invite(edition, chair, "pro@univ.ci")
    user = VerifiedUserFactory(email="perso@example.org")
    client = client_for(user)
    assert post(client, "link-email", {"token": token}).status_code == 204
    link = _link_from_last_email("pro@univ.ci")
    response = post(client, "accept", {"link": link})
    assert response.status_code == 200
    assert EmailAddress.objects.get(user=user, email="pro@univ.ci").verified
    assert UserRole.objects.get(user=user).role == Role.SC_MEMBER
    notification = OutboxEmail.objects.get(template_code="account/email/email_added")
    assert notification.to_email == "perso@example.org"
    assert AuditLog.objects.filter(action="account.email_linked").exists()


def test_rg20_link_token_bound_to_requesting_account(edition, chair):
    token = invite(edition, chair, "pro@univ.ci")
    requester = VerifiedUserFactory()
    post(client_for(requester), "link-email", {"token": token})
    link = _link_from_last_email("pro@univ.ci")
    thief = VerifiedUserFactory()
    response = post(client_for(thief), "accept", {"link": link})
    assert response.status_code == 400
    assert response.json()["code"] == "invitation_link_invalid"
    assert post(client_for(requester), "accept", {"link": link + "x"}).json()["code"] == (
        "invitation_link_invalid"
    )
    assert not UserRole.objects.filter(role=Role.SC_MEMBER).exists()


def test_rg20_link_requires_recent_reauth_and_notifies_primary(edition, chair):
    token = invite(edition, chair, "pro@univ.ci")
    user = VerifiedUserFactory()
    stale = client_for(user, recent_auth=False)
    response = post(stale, "link-email", {"token": token})
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"
    post(client_for(user), "link-email", {"token": token})
    link = _link_from_last_email("pro@univ.ci")
    response = post(client_for(user, recent_auth=False), "accept", {"link": link})
    assert response.status_code == 403
    assert response.json()["code"] == "reauthentication_required"
    assert not EmailAddress.objects.filter(email="pro@univ.ci").exists()


def test_rg20_link_respects_address_limit(edition, chair):
    token = invite(edition, chair, "pro@univ.ci")
    user = VerifiedUserFactory()
    for n in range(2):
        EmailAddress.objects.create(user=user, email=f"autre{n}@example.org", verified=True)
    client = client_for(user)
    post(client, "link-email", {"token": token})
    link = _link_from_last_email("pro@univ.ci")
    response = post(client, "accept", {"link": link})
    assert response.status_code == 409
    assert response.json()["code"] == "email_address_limit"


def test_link_email_throttled(edition, chair, settings):
    token = invite(edition, chair, "pro@univ.ci")
    client = client_for(VerifiedUserFactory())
    codes = [post(client, "link-email", {"token": token}).status_code for _ in range(4)]
    assert codes == [204, 204, 204, 429]


# --- Renvoi, annulation, expiration --------------------------------------------------------


def test_resend_rotates_token_and_cancel(edition, chair):
    old = invite(edition, chair, "awa@univ.ci")
    invitation = RoleInvitation.objects.get()
    client = client_for(chair)
    base = f"/v1/manage/editions/{edition.pk}/invitations/{invitation.pk}"
    assert client.post(f"{base}/resend").status_code == 200
    assert post(APIClient(), "lookup", {"token": old}).status_code == 404
    assert client.post(f"{base}/cancel").json()["status"] == "cancelled"
    assert client.post(f"{base}/cancel").json()["code"] == "invitation_not_pending"
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {"invitation.resent", "invitation.cancelled"} <= actions


def test_cleanup_expires_due_invitations(edition, chair):
    invite(edition, chair, "awa@univ.ci")
    RoleInvitation.objects.update(expires_at=timezone.now() - dt.timedelta(days=1))
    assert service.expire_due_invitations(True, timezone.now()) == 1
    assert service.expire_due_invitations(False, timezone.now()) == 1
    invitation = RoleInvitation.objects.get()
    assert (invitation.status, invitation.pending_key) == ("expired", None)


def test_me_lists_pending_invitations_and_roles(edition, chair):
    invite(edition, chair, "awa@univ.ci")
    owner = VerifiedUserFactory(email="awa@univ.ci")
    body = client_for(owner).get("/v1/me").json()
    assert [item["role"] for item in body["pending_invitations"]] == ["SC_MEMBER"]
    me_chair = client_for(chair).get("/v1/me").json()
    assert me_chair["editions"][0]["id"] == edition.pk
    assert me_chair["editions"][0]["roles"] == [{"role": "CHAIR", "oc_function": ""}]
    assert "edition.publish" in me_chair["editions"][0]["capabilities"]
    assert me_chair["editions"][0]["mfa_required"] is True
