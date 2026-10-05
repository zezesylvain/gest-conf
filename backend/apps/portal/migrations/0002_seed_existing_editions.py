"""Seed des éditions existantes : pages du site (marquées ``is_system`` d'après
``SITE_ROUTES``), sections « données », menu d'en-tête ; aucune composition.

Modèles historiques seulement ; les données viennent de ``apps.portal.site`` (pur Python).
"""

from django.db import migrations

from apps.portal.site import SEED_HEADER_MENU, SEED_SECTIONS, SITE_PAGES, SITE_ROUTES


def seed(apps, schema_editor):
    Edition = apps.get_model("conferences", "Edition")
    Page = apps.get_model("portal", "Page")
    Section = apps.get_model("portal", "Section")
    MenuItem = apps.get_model("portal", "MenuItem")
    for edition in Edition.objects.all():
        pages = {page.slug: page for page in Page.objects.filter(edition=edition)}
        for site_page in SITE_PAGES:
            if site_page.slug not in pages:
                pages[site_page.slug] = Page.objects.create(
                    edition=edition,
                    slug=site_page.slug,
                    is_system=True,
                    title_fr=site_page.title_fr,
                    title_en=site_page.title_en,
                )
        Page.objects.filter(edition=edition, slug__in=list(SITE_ROUTES)).update(is_system=True)
        keys = set(Section.objects.filter(edition=edition).values_list("code", flat=True))
        for code, section_type, title_fr, title_en, config in SEED_SECTIONS:
            if code not in keys:
                Section.objects.create(
                    edition=edition,
                    code=code,
                    section_type=section_type,
                    title_fr=title_fr,
                    title_en=title_en,
                    config=dict(config),
                )
        if not MenuItem.objects.filter(edition=edition).exists():
            for position, slug in enumerate(SEED_HEADER_MENU):
                MenuItem.objects.create(
                    edition=edition,
                    location="header",
                    label_fr=pages[slug].title_fr,
                    label_en=pages[slug].title_en,
                    page=pages[slug],
                    position=position,
                )


class Migration(migrations.Migration):
    dependencies = [("portal", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
