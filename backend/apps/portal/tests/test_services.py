"""Services du CMS du portail (plan L2 §2.2, §7)."""

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.conferences.models import EditionStatus
from apps.conferences.services import update_edition
from apps.conferences.tests.factories import EditionFactory
from apps.core.actor import Actor
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.portal import services
from apps.portal.models import MenuItem, Page, PageSection, Publication, Section
from apps.portal.site import SEED_HEADER_MENU, SEED_SECTIONS, SITE_PAGES

pytestmark = pytest.mark.django_db

ACTOR = Actor.command("cli:test")


def rich(edition, code="texte", **fields):
    return services.create_section(
        edition, {"code": code, "section_type": "rich_text", **fields}, actor=ACTOR
    )


def custom_page(edition, slug="infos"):
    return services.create_page(edition, {"slug": slug, "title_fr": "Infos"}, actor=ACTOR)


# --- Seed --------------------------------------------------------------------------------------


def test_seed_at_edition_creation_without_composition():
    """Le seed livre pages du site, sections « données » et menu ; aucune composition."""
    edition = EditionFactory()
    pages = Page.objects.filter(edition=edition)
    assert sorted(pages.values_list("slug", flat=True)) == sorted(p.slug for p in SITE_PAGES)
    assert all(page.is_system for page in pages)
    assert Section.objects.filter(edition=edition).count() == len(SEED_SECTIONS)
    assert not PageSection.objects.filter(page__edition=edition).exists()
    header = MenuItem.objects.filter(edition=edition, location="header").order_by("position")
    assert [item.page.slug for item in header] == list(SEED_HEADER_MENU)


def test_seed_is_idempotent_and_respects_deleted_menus():
    edition = EditionFactory()
    MenuItem.objects.filter(edition=edition).delete()
    Section.objects.filter(edition=edition, code="documents").delete()
    created = services.seed_portal(edition)
    assert created == {"pages": 0, "sections": 1, "menu_items": len(SEED_HEADER_MENU)}
    assert services.seed_portal(edition) == {"pages": 0, "sections": 0, "menu_items": 0}


def test_seed_portal_command_audits_only_when_something_is_created():
    edition = EditionFactory()
    call_command("seed_portal", edition.code)
    assert not AuditLog.objects.filter(action="portal.seeded").exists()
    Section.objects.filter(edition=edition, code="tracks").delete()
    call_command("seed_portal", edition.code)
    assert AuditLog.objects.get(action="portal.seeded").after["sections"] == 1


# --- Sections ----------------------------------------------------------------------------------


def test_section_html_sanitized_on_write():
    edition = EditionFactory()
    section = rich(edition, body_fr='<p onclick="x()">Bonjour<script>alert(1)</script></p>')
    assert section.body_fr == "<p>Bonjour</p>"


def test_section_config_is_bounded_by_type():
    edition = EditionFactory()
    with pytest.raises(Invalid) as error:
        services.create_section(
            edition, {"code": "comite", "section_type": "committee", "config": {}}, actor=ACTOR
        )
    assert "config" in error.value.fields
    with pytest.raises(Invalid):
        rich(edition, config={"limit": 3})
    with pytest.raises(Invalid):
        services.create_section(
            edition,
            {"code": "dates", "section_type": "key_dates", "config": {"limit": 999}},
            actor=ACTOR,
        )
    section = services.create_section(
        edition,
        {"code": "dates2", "section_type": "key_dates", "config": {"limit": 3}},
        actor=ACTOR,
    )
    assert section.config == {"limit": 3}


def test_data_section_has_no_body():
    edition = EditionFactory()
    with pytest.raises(Invalid):
        services.create_section(
            edition,
            {"code": "t2", "section_type": "tracks", "body_fr": "<p>copie</p>"},
            actor=ACTOR,
        )


def test_cta_url_allowlist():
    edition = EditionFactory()
    with pytest.raises(Invalid) as error:
        rich(edition, cta_label_fr="Go", cta_url="javascript:alert(1)")
    assert "cta_url" in error.value.fields
    assert rich(edition, code="ok", cta_url="/fr/appel/").cta_url == "/fr/appel/"


def test_section_type_is_immutable():
    edition = EditionFactory()
    section = rich(edition)
    with pytest.raises(Invalid):
        services.update_section(section, {"section_type": "cta_banner"}, actor=ACTOR)


def test_section_update_only_audits_real_changes():
    edition = EditionFactory()
    section = rich(edition, body_fr="<p>x</p>")
    services.update_section(section, {"body_fr": "<p>x</p>"}, actor=ACTOR)
    assert not AuditLog.objects.filter(action="portal.section_updated").exists()
    services.update_section(section, {"title_fr": "Titre"}, actor=ACTOR)
    entry = AuditLog.objects.get(action="portal.section_updated")
    assert entry.before == {"title_fr": ""} and entry.after == {"title_fr": "Titre"}


def test_emails_masked_in_audit():
    """Le journal refuse les adresses en clair : elles y sont masquées, pas en base."""
    edition = EditionFactory()
    section = rich(
        edition, body_fr='<p><a href="mailto:contact@conf.example">contact@conf.example</a></p>'
    )
    assert "contact@conf.example" in section.body_fr
    after = AuditLog.objects.get(action="portal.section_created").after
    assert "contact@" not in after["body_fr"] and "c***@conf.example" in after["body_fr"]


def test_section_placed_cannot_be_deleted_and_names_pages():
    edition = EditionFactory()
    section = rich(edition)
    page = custom_page(edition)
    services.attach_section(page, section, actor=ACTOR)
    with pytest.raises(Invalid) as error:
        services.delete_section(section, actor=ACTOR)
    assert "infos" in str(error.value.fields["non_field_errors"][0])
    services.detach_section(page, section, actor=ACTOR)
    services.delete_section(section, actor=ACTOR)
    assert not Section.objects.filter(pk=section.pk).exists()


# --- Pages ---------------------------------------------------------------------------------------


def test_custom_page_cannot_take_a_site_slug():
    edition = EditionFactory()
    with pytest.raises(Invalid):
        services.create_page(edition, {"slug": "call", "title_fr": "Appel"}, actor=ACTOR)


def test_system_page_slug_locked_and_not_deletable():
    edition = EditionFactory()
    home = Page.objects.get(edition=edition, slug="home")
    with pytest.raises(Invalid):
        services.update_page(home, {"slug": "accueil"}, actor=ACTOR)
    with pytest.raises(Invalid):
        services.update_page(home, {"published": False}, actor=ACTOR)
    assert services.update_page(home, {"title_en": "Welcome"}, actor=ACTOR).title_en == "Welcome"
    with pytest.raises(RuleViolation):
        services.delete_page(home, actor=ACTOR)


def test_page_in_a_menu_cannot_be_deleted():
    edition = EditionFactory()
    page = custom_page(edition)
    services.create_menu_item(
        edition, {"location": "footer", "label_fr": "Infos", "page": page}, actor=ACTOR
    )
    with pytest.raises(RuleViolation):
        services.delete_page(page, actor=ACTOR)


def test_paths_have_trailing_slash_and_no_p_duplicate_for_site_pages():
    edition = EditionFactory()
    custom_page(edition)
    routes = services.public_routes(edition)
    assert "/fr/" in routes and "/en/" in routes
    assert "/fr/appel/" in routes and "/en/call/" in routes
    assert "/fr/p/infos/" in routes and "/en/p/infos/" in routes
    assert not any(route.startswith(("/fr/p/call", "/fr/p/home")) for route in routes)
    assert len(routes) == len(set(routes)) == 2 * (len(SITE_PAGES) + 1)


def test_unpublished_custom_page_is_not_routed():
    edition = EditionFactory()
    services.create_page(
        edition, {"slug": "brouillon", "title_fr": "B", "published": False}, actor=ACTOR
    )
    assert "/fr/p/brouillon/" not in services.public_routes(edition)


# --- Composition ----------------------------------------------------------------------------------


def test_composition_attach_detach_reorder_reread_from_database():
    edition = EditionFactory()
    page = custom_page(edition)
    a, b, c = (rich(edition, code=code) for code in ("a", "b", "c"))
    services.attach_section(page, a, actor=ACTOR)
    services.attach_section(page, b, actor=ACTOR)
    result = services.attach_section(page, c, position=0, actor=ACTOR)
    assert [placement.section.code for placement in result] == ["c", "a", "b"]
    assert [placement.position for placement in result] == [0, 1, 2]
    result = services.reorder_sections(page, [a.pk, b.pk, c.pk], actor=ACTOR)
    assert [placement.section.code for placement in result] == ["a", "b", "c"]
    result = services.detach_section(page, b, actor=ACTOR)
    assert [placement.section.code for placement in result] == ["a", "c"]
    assert [placement.position for placement in result] == [0, 1]
    entries = AuditLog.objects.filter(action="portal.page_composed").order_by("id")
    assert entries.last().before == {"sections": [a.pk, b.pk, c.pk]}
    assert entries.last().after == {"sections": [a.pk, c.pk]}


@pytest.mark.parametrize("order", [[], ["a"], ["a", "a"], ["a", "b", "x"]])
def test_reorder_requires_the_exact_full_list(order):
    edition = EditionFactory()
    page = custom_page(edition)
    sections = {code: rich(edition, code=code) for code in ("a", "b", "x")}
    services.attach_section(page, sections["a"], actor=ACTOR)
    services.attach_section(page, sections["b"], actor=ACTOR)
    with pytest.raises(Invalid):
        services.reorder_sections(page, [sections[code].pk for code in order], actor=ACTOR)


def test_attach_refuses_duplicate_and_other_edition():
    edition = EditionFactory()
    page = custom_page(edition)
    section = rich(edition)
    services.attach_section(page, section, actor=ACTOR)
    with pytest.raises(Invalid):
        services.attach_section(page, section, actor=ACTOR)
    with pytest.raises(Invalid):
        services.attach_section(page, rich(EditionFactory(), code="ailleurs"), actor=ACTOR)


# --- Menus ----------------------------------------------------------------------------------------


def test_menu_item_page_xor_url():
    edition = EditionFactory()
    page = custom_page(edition)
    with pytest.raises(Invalid):
        services.create_menu_item(
            edition,
            {"location": "footer", "label_fr": "x", "page": page, "url": "https://x.example"},
            actor=ACTOR,
        )
    with pytest.raises(Invalid):
        services.create_menu_item(edition, {"location": "footer", "label_fr": "x"}, actor=ACTOR)
    with pytest.raises(Invalid):
        services.create_menu_item(
            edition, {"location": "footer", "label_fr": "x", "url": "javascript:x"}, actor=ACTOR
        )
    item = services.create_menu_item(
        edition, {"location": "footer", "label_fr": "Site", "url": "https://x.example"}, actor=ACTOR
    )
    assert item.position == 0


def test_menu_reorder_full_list():
    edition = EditionFactory()
    ids = list(
        MenuItem.objects.filter(edition=edition, location="header")
        .order_by("position")
        .values_list("pk", flat=True)
    )
    result = services.reorder_menu(edition, "header", list(reversed(ids)), actor=ACTOR)
    assert [item.pk for item in result] == list(reversed(ids))
    with pytest.raises(Invalid):
        services.reorder_menu(edition, "header", ids[:-1], actor=ACTOR)


# --- Édition archivée -----------------------------------------------------------------------------


def test_archived_edition_is_read_only():
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    with pytest.raises(RuleViolation):
        rich(edition)
    with pytest.raises(RuleViolation):
        services.preview_html(edition, "<p>x</p>")


# --- Publication (E1, E9) ----------------------------------------------------------------------


def test_pending_changes_counted_since_last_publication():
    edition = EditionFactory()
    assert services.publication_status(edition)["pending_changes"] == 0
    rich(edition)
    update_edition(edition, {"venue": "Palais de la culture"}, actor=ACTOR)
    status = services.publication_status(edition)
    assert status["pending_changes"] == 2
    assert status["last_published_at"] is None
    call_command("mark_portal_published", edition.code, "--release", "abc123")
    status = services.publication_status(edition)
    assert status["pending_changes"] == 0
    assert status["release"] == "abc123"
    assert Publication.objects.filter(edition=edition).count() == 1
    rich(edition, code="autre")
    assert services.publication_status(edition)["pending_changes"] == 1


def test_changes_of_other_editions_or_unrelated_actions_are_not_counted():
    edition = EditionFactory()
    rich(EditionFactory(), code="ailleurs")
    from apps.core.audit import record

    record("role.granted", actor=ACTOR, edition=edition)
    assert services.publication_status(edition)["pending_changes"] == 0


def test_program_publication_counts_but_program_draft_does_not():
    """Plan L5, I7 : le programme public est pré-rendu ; sa publication rend le portail à
    republier, pas les modifications du brouillon."""
    from apps.core.audit import record

    edition = EditionFactory()
    record("program.session_created", actor=ACTOR, edition=edition)
    record("program.settings_changed", actor=ACTOR, edition=edition)
    assert services.publication_status(edition)["pending_changes"] == 0
    record("program.published", actor=ACTOR, edition=edition)
    assert services.publication_status(edition)["pending_changes"] == 1


def test_pending_since_is_the_oldest_pending_change():
    edition = EditionFactory()
    rich(edition)
    rich(edition, code="b")
    times = AuditLog.objects.filter(action="portal.section_created").values_list("at", flat=True)
    assert services.publication_status(edition)["pending_since"] == min(times)


def test_site_pages_are_identical_in_the_portal():
    """``SITE_PAGES`` est recopiée pour Angular (routes statiques du portail) : les deux
    listes doivent rester identiques (adresses figées des pages du site)."""
    import json
    from pathlib import Path

    from django.conf import settings

    path = Path(settings.BASE_DIR).parent / "web/projects/portail/src/app/site/site-pages.json"
    expected = [
        {
            "slug": page.slug,
            "fr": page.path_fr,
            "en": page.path_en,
            "title_fr": page.title_fr,
            "title_en": page.title_en,
            "coming_soon": page.coming_soon,
        }
        for page in SITE_PAGES
    ]
    assert json.loads(path.read_text(encoding="utf-8")) == expected


def test_changes_made_during_the_build_stay_pending():
    """E9 : la mise en ligne est datée du début du pré-rendu (``--built-at``)."""
    edition = EditionFactory()
    built_at = timezone.now()
    rich(edition)  # modifiée pendant le build : peut-être absente du portail publié
    call_command("mark_portal_published", edition.code, "--built-at", built_at.isoformat())
    assert services.publication_status(edition)["pending_changes"] == 1
    with pytest.raises(CommandError):
        call_command("mark_portal_published", edition.code, "--built-at", "2026-10-05T10:00")
    with pytest.raises(CommandError):
        call_command("mark_portal_published", edition.code, "--built-at", "hier")
