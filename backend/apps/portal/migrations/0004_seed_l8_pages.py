"""Pages du site ajoutées en L8 (N5, N10) : « Partenaires » et « Actualités », créées pour
les éditions existantes et marquées ``is_system`` ; menus existants inchangés (le CMS les
compose). Une page personnalisée qui portait déjà l'un de ces slugs devient page du site,
comme en 0002.
"""

from django.db import migrations

NEW_PAGES = (
    ("sponsors", "Partenaires", "Partners"),
    ("news", "Actualités", "News"),
)


def seed(apps, schema_editor):
    Edition = apps.get_model("conferences", "Edition")
    Page = apps.get_model("portal", "Page")
    slugs = [slug for slug, _fr, _en in NEW_PAGES]
    for edition in Edition.objects.all():
        existing = set(
            Page.objects.filter(edition=edition, slug__in=slugs).values_list("slug", flat=True)
        )
        for slug, title_fr, title_en in NEW_PAGES:
            if slug not in existing:
                Page.objects.create(
                    edition=edition,
                    slug=slug,
                    is_system=True,
                    title_fr=title_fr,
                    title_en=title_en,
                )
    Page.objects.filter(slug__in=slugs).update(is_system=True)


class Migration(migrations.Migration):
    dependencies = [("portal", "0003_section_image")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
