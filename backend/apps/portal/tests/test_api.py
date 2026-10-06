"""API du CMS du portail (plan L2 §4) : lecture publique et gestion."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import Conference, EditionStatus
from apps.conferences.tests.factories import EditionFactory, TrackFactory
from apps.core.actor import Actor
from apps.portal import services
from apps.portal.models import MenuItem, Page, Section
from apps.portal.site import SITE_PAGES

pytestmark = pytest.mark.django_db

ACTOR = Actor.command("cli:test")


@pytest.fixture
def public_edition():
    edition = EditionFactory(status=EditionStatus.PUBLISHED)
    Conference.objects.filter(pk=edition.conference_id).update(current_edition=edition)
    TrackFactory(edition=edition, name_fr="IA", is_active=True)
    return edition


def _public(path: str):
    return APIClient().get(f"/v1/public/portal/{path}")


# --- Public --------------------------------------------------------------------------------------


def test_public_endpoints_404_without_published_current_edition():
    EditionFactory()  # brouillon, non courante
    for path in ("routes", "site", "pages/home", "menu?location=header"):
        assert _public(path).status_code == 404, path


def test_routes_with_expected_count(public_edition):
    services.create_page(public_edition, {"slug": "infos", "title_fr": "Infos"}, actor=ACTOR)
    response = _public("routes")
    assert response.status_code == 200
    assert response["Cache-Control"] == "public, max-age=300"
    body = response.json()
    assert body["expected"] == len(body["routes"]) == 2 * (len(SITE_PAGES) + 1)
    assert {"/fr/", "/en/", "/fr/p/infos/", "/en/p/infos/"} <= set(body["routes"])
    assert {page["slug"] for page in body["pages"]} >= {"home", "infos"}
    assert body["alternates"] == []  # programme non publié : aucune page du programme


def test_composition_lists_only_published_sections_in_order(public_edition):
    page = Page.objects.get(edition=public_edition, slug="home")
    hero = Section.objects.get(edition=public_edition, code="hero")
    text = services.create_section(
        public_edition,
        {"code": "intro", "section_type": "rich_text", "body_fr": "<p>Bienvenue</p>"},
        actor=ACTOR,
    )
    hidden = services.create_section(
        public_edition,
        {"code": "cache", "section_type": "rich_text", "published": False},
        actor=ACTOR,
    )
    for section in (text, hero, hidden):
        services.attach_section(page, section, actor=ACTOR)
    body = _public("pages/home").json()
    assert body["page"]["paths"] == {"fr": "/fr/", "en": "/en/"}
    assert [section["code"] for section in body["sections"]] == ["intro", "hero"]
    assert body["sections"][0]["body_fr"] == "<p>Bienvenue</p>"
    assert body["sections"][0]["data"] is None
    assert body["sections"][1]["data"]["code"] == public_edition.code


def test_data_sections_read_live_data_never_a_copy(public_edition):
    page = services.create_page(public_edition, {"slug": "infos", "title_fr": "I"}, actor=ACTOR)
    services.attach_section(
        page, Section.objects.get(edition=public_edition, code="tracks"), actor=ACTOR
    )
    data = _public("pages/infos").json()["sections"][0]["data"]
    assert [track["name_fr"] for track in data] == ["IA"]
    TrackFactory(edition=public_edition, name_fr="Réseaux", position=1)
    data = _public("pages/infos").json()["sections"][0]["data"]
    assert [track["name_fr"] for track in data] == ["IA", "Réseaux"]


def test_unpublished_custom_page_is_404(public_edition):
    services.create_page(
        public_edition, {"slug": "brouillon", "title_fr": "B", "published": False}, actor=ACTOR
    )
    assert _public("pages/brouillon").status_code == 404
    assert _public("pages/inconnue").status_code == 404


def test_menu_hrefs_by_language_and_unpublished_targets_omitted(public_edition):
    draft = services.create_page(
        public_edition, {"slug": "brouillon", "title_fr": "B", "published": False}, actor=ACTOR
    )
    services.create_menu_item(
        public_edition, {"location": "header", "label_fr": "B", "page": draft}, actor=ACTOR
    )
    services.create_menu_item(
        public_edition,
        {"location": "footer", "label_fr": "Site", "url": "https://x.example", "new_tab": True},
        actor=ACTOR,
    )
    header = _public("menu?location=header").json()
    assert header[0] == {
        "label_fr": "Appel à communications",
        "label_en": "Call for papers",
        "href_fr": "/fr/appel/",
        "href_en": "/en/call/",
        "new_tab": False,
        "page": "call",
    }
    assert "brouillon" not in [item["page"] for item in header]
    footer = _public("menu?location=footer").json()
    assert footer == [
        {
            "label_fr": "Site",
            "label_en": "",
            "href_fr": "https://x.example",
            "href_en": "https://x.example",
            "new_tab": True,
            "page": None,
        }
    ]
    assert _public("menu?location=side").status_code == 404


def test_site_data(public_edition):
    body = _public("site").json()
    assert body["edition"]["code"] == public_edition.code
    assert body["documents"] == []
    empty = {"members": [], "others": 0}
    assert body["committees"] == {"scientific": empty, "organizing": empty}


# --- Gestion ------------------------------------------------------------------------------------


def _manage(edition, path: str) -> str:
    return f"/v1/manage/editions/{edition.pk}/portal/{path}"


def test_section_list_shows_pages_without_n_plus_one(django_assert_max_num_queries):
    edition = EditionFactory()
    chair = make_member(edition, Role.CHAIR)
    client = client_for(chair)
    page = Page.objects.get(edition=edition, slug="home")
    for section in Section.objects.filter(edition=edition):
        services.attach_section(page, section, actor=ACTOR)
    with django_assert_max_num_queries(12):
        body = client.get(_manage(edition, "sections")).json()
    assert len(body) == Section.objects.filter(edition=edition).count()
    assert all(
        item["pages"] == [{"id": page.pk, "slug": "home", "title_fr": "Accueil", "is_system": True}]
        for item in body
    )


def test_page_detail_and_composition_actions():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.CHAIR))
    page_id = client.post(
        _manage(edition, "pages"), {"slug": "infos", "title_fr": "Infos"}, format="json"
    ).json()["id"]
    a = Section.objects.get(edition=edition, code="tracks")
    b = Section.objects.get(edition=edition, code="key-dates")
    client.post(_manage(edition, f"pages/{page_id}/attach"), {"section": a.pk}, format="json")
    body = client.post(
        _manage(edition, f"pages/{page_id}/attach"), {"section": b.pk, "position": 0}, format="json"
    ).json()
    assert [item["section"]["code"] for item in body["sections"]] == ["key-dates", "tracks"]
    assert body["paths"] == {"fr": "/fr/p/infos/", "en": "/en/p/infos/"}
    response = client.post(
        _manage(edition, f"pages/{page_id}/reorder"), {"sections": [a.pk]}, format="json"
    )
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"
    response = client.delete(_manage(edition, f"sections/{a.pk}"))
    assert response.status_code == 400
    assert "infos" in response.json()["fields"]["non_field_errors"][0]
    other = Section.objects.create(edition=EditionFactory(), code="x", section_type="rich_text")
    response = client.post(
        _manage(edition, f"pages/{page_id}/attach"), {"section": other.pk}, format="json"
    )
    assert response.status_code == 404


def test_preview_returns_sanitized_html_without_writing():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.CHAIR))
    count = Section.objects.count()
    body = client.post(
        _manage(edition, "sections/preview"),
        {"body_fr": "<p>ok<script>x</script></p>"},
        format="json",
    ).json()
    assert body == {"body_fr": "<p>ok</p>", "body_en": ""}
    assert Section.objects.count() == count


def test_menu_list_filter_and_status():
    edition = EditionFactory()
    client = client_for(make_member(edition, Role.OC_MEMBER))  # lecture seule
    header = client.get(_manage(edition, "menu?location=header")).json()
    assert len(header) == MenuItem.objects.filter(edition=edition, location="header").count()
    assert client.get(_manage(edition, "menu?location=footer")).json() == []
    status = client.get(_manage(edition, "status")).json()
    assert status == {
        "last_published_at": None,
        "release": "",
        "pending_changes": 0,
        "pending_since": None,
    }


def test_oc_communication_has_portal_write_in_me():
    """E11 : la capacité vient de la fonction « communication » au CO, pas du rôle seul."""
    edition = EditionFactory()
    communication = make_member(edition, Role.OC_MEMBER, oc_function="communication")
    finance = make_member(edition, Role.OC_MEMBER, oc_function="finance")
    capabilities = client_for(communication).get("/v1/me").json()["editions"][0]["capabilities"]
    assert "portal.write" in capabilities
    capabilities = client_for(finance).get("/v1/me").json()["editions"][0]["capabilities"]
    assert "portal.write" not in capabilities
