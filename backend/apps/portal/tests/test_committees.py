"""Comités publics (L2.6, E5) : membres actifs consentants, jamais d'adresse."""

import io
import json

import pytest
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import ConsentKind, ConsentSource, Profile, UserRoleStatus
from apps.accounts.roles import OcFunction, Role
from apps.accounts.services.account import record_consent
from apps.accounts.services.profile import set_photo
from apps.accounts.tests.roles_helpers import make_member
from apps.conferences.models import Conference, EditionStatus
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.portal import services
from apps.portal.models import Page, Section

pytestmark = pytest.mark.django_db

ACTOR = Actor.command("cli:test")


@pytest.fixture
def edition():
    edition = EditionFactory(status=EditionStatus.PUBLISHED)
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    return edition


def member(edition, role, first, last, *, listed=True, oc_function=None, **profile):
    user = make_member(edition, role, oc_function=oc_function)
    Profile.objects.create(user=user, first_name=first, last_name=last, **profile)
    if listed:
        consent(user, ConsentKind.DIRECTORY_LISTING, True)
    return user


def consent(user, kind, granted):
    record_consent(user, kind, granted, source=ConsentSource.ACCOUNT, actor=ACTOR)


def png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (40, 40), "teal").save(output, "PNG")
    return output.getvalue()


def site():
    return APIClient().get("/v1/public/portal/site").json()["committees"]


def test_rg_e5_only_consenting_active_members_are_listed(edition):
    member(edition, Role.SC_MEMBER, "Awa", "Zadi", institution="Univ. FHB", country="CI")
    member(edition, Role.SC_CHAIR, "Koffi", "Yao", title="pr")
    member(edition, Role.SC_MEMBER, "Sans", "Consentement", listed=False)
    revoked = member(edition, Role.SC_MEMBER, "Ancien", "Membre")
    revoked.roles.update(status=UserRoleStatus.REVOKED)
    withdrawn = member(edition, Role.SC_MEMBER, "Retrait", "Annuaire")
    consent(withdrawn, ConsentKind.DIRECTORY_LISTING, False)
    inactive = member(edition, Role.SC_MEMBER, "Compte", "Inactif")
    inactive.is_active = False
    inactive.save()
    member(EditionFactory(), Role.SC_MEMBER, "Autre", "Edition")
    scientific = site()["scientific"]
    # Présidence d'abord, puis par nom de famille.
    assert [m["name"] for m in scientific["members"]] == ["Koffi Yao", "Awa Zadi"]
    assert scientific["members"][0] == {
        "title": "pr",
        "name": "Koffi Yao",
        "chair": True,
        "function": "",
        "institution": "",
        "country": "",
        "website": "",
        "scholar_url": "",
        "linkedin_url": "",
        "photo_url": None,
    }
    assert scientific["members"][1]["institution"] == "Univ. FHB"
    assert scientific["others"] == 2  # sans consentement, retrait
    assert site()["organizing"] == {"members": [], "others": 0}


def test_rg_e5_no_email_anywhere(edition):
    user = member(edition, Role.OC_MEMBER, "Ama", "Kone", oc_function=OcFunction.LOGISTICS)
    body = APIClient().get("/v1/public/portal/site").content.decode()
    assert user.email not in body and "@" not in json.dumps(site())
    organizing = site()["organizing"]["members"]
    assert organizing[0]["function"] == "logistics" and organizing[0]["chair"] is False


def test_rg_e5_chair_in_organizing_and_one_entry_per_committee(edition):
    chair = member(edition, Role.CHAIR, "Paul", "Achi")
    make_member_role(chair, edition, Role.OC_MEMBER)
    member(edition, Role.OC_MEMBER, "Ines", "Bamba")
    organizing = site()["organizing"]["members"]
    assert [(m["name"], m["chair"]) for m in organizing] == [
        ("Paul Achi", True),
        ("Ines Bamba", False),
    ]


def make_member_role(user, edition, role):
    from django.utils import timezone

    from apps.accounts.models import RoleSource, UserRole

    UserRole.objects.create(
        user=user,
        edition=edition,
        role=role,
        oc_function=OcFunction.PROGRAM if role == Role.OC_MEMBER else "",
        source=RoleSource.COMMAND,
        granted_at=timezone.now(),
    )


def test_rg_e5_photo_needs_its_own_consent(edition, django_capture_on_commit_callbacks):
    user = member(edition, Role.SC_MEMBER, "Awa", "Zadi", website="https://awa.example")
    set_photo(user, data=png(), name="a.png", actor=ACTOR)
    entry = site()["scientific"]["members"][0]
    assert entry["photo_url"] is None and entry["website"] == "https://awa.example"
    consent(user, ConsentKind.PHOTO_PUBLICATION, True)
    url = site()["scientific"]["members"][0]["photo_url"]
    assert url and APIClient().get(url).status_code == 200


def test_committee_section_data(edition):
    member(edition, Role.SC_MEMBER, "Awa", "Zadi")
    section = Section.objects.get(edition=edition, code="committee-scientific")
    page = Page.objects.get(edition=edition, slug="committees")
    services.attach_section(page, section, actor=ACTOR)
    data = APIClient().get("/v1/public/portal/pages/committees").json()["sections"][0]["data"]
    assert [m["name"] for m in data["members"]] == ["Awa Zadi"] and data["others"] == 0


def test_committee_changes_count_as_unpublished(edition):
    services.mark_published(edition, actor=ACTOR)
    assert services.publication_status(edition)["pending_changes"] == 0
    # Rôle créé sans service (non journalisé) : seul le consentement compte.
    user = member(edition, Role.SC_MEMBER, "Awa", "Zadi")
    assert services.publication_status(edition)["pending_changes"] == 1
    services.mark_published(edition, actor=ACTOR)
    consent(user, ConsentKind.DIRECTORY_LISTING, False)
    assert services.publication_status(edition)["pending_changes"] == 1
    outsider = make_member(EditionFactory(), Role.SC_MEMBER)
    consent(outsider, ConsentKind.DIRECTORY_LISTING, True)  # autre édition : sans effet
    assert services.publication_status(edition)["pending_changes"] == 1


def test_committee_queries_do_not_grow_with_members(edition, django_assert_max_num_queries):
    for index in range(6):
        member(edition, Role.SC_MEMBER, f"P{index}", f"N{index}")
    with django_assert_max_num_queries(3):
        services.public_committees(edition)


def test_committee_role_grants_count_as_unpublished_others_do_not(edition):
    from apps.accounts.models import RoleSource
    from apps.accounts.services.roles import grant_role
    from apps.accounts.tests.factories import VerifiedUserFactory

    services.mark_published(edition, actor=ACTOR)
    for role in (Role.SC_MEMBER, Role.AUTHOR):
        grant_role(
            user=VerifiedUserFactory(),
            edition=edition,
            role=role,
            actor=ACTOR,
            source=RoleSource.COMMAND,
        )
    assert services.publication_status(edition)["pending_changes"] == 1
