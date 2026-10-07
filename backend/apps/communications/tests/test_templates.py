"""Gabarits d'e-mails du projet (plan L1 §8.3) : objets sans donnée de personne, FR/EN."""

from pathlib import Path

import pytest
from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation

from apps.communications.services import (
    ALLOWED_CONTEXT_KEYS,
    EMAIL_TEMPLATES,
    SITE_NAME_KEY,
)

APPS_DIR = Path(settings.BASE_DIR) / "apps"


def project_subject_templates() -> list[str]:
    """Tous les gabarits d'objet du projet (apps/*/templates/**/*_subject.txt)."""
    names = []
    for templates_dir in APPS_DIR.glob("*/templates"):
        names += [
            path.relative_to(templates_dir).as_posix()
            for path in templates_dir.rglob("*_subject.txt")
        ]
    return sorted(names)


def sentinel_context() -> dict[str, str]:
    """Une valeur sentinelle par clé admise ; le nom du site, fixe, n'est pas une donnée de
    personne et garde sa vraie valeur."""
    context = {key: f"ZZSENTINELLE-{key}-ZZ" for key in ALLOWED_CONTEXT_KEYS}
    context["display_name"] = "Jeanne SENTINELLE-NOM"
    context[SITE_NAME_KEY] = settings.GESTCONF_SITE_NAME
    return context


def test_every_registered_template_exists_in_both_languages():
    for template in EMAIL_TEMPLATES.values():
        for name in template.template_names():
            for language in ("fr", "en"):
                with translation.override(language):
                    assert render_to_string(name, sentinel_context()).strip(), name


def test_subject_templates_are_all_found():
    found = project_subject_templates()
    assert "communications/email/test_email_subject.txt" in found
    registered = {f"{template.prefix}_subject.txt" for template in EMAIL_TEMPLATES.values()}
    assert registered <= set(found)


@pytest.mark.parametrize("language", ["fr", "en"])
@pytest.mark.parametrize("name", project_subject_templates())
def test_subject_templates_have_no_personal_data(name, language):
    """§8.3 v3 : l'objet est conservé 12 mois avec les métadonnées d'envoi, alors que les
    corps sont purgés. Aucun gabarit d'objet n'utilise display_name, adresse, IP, lien ou
    nom de l'invitant : rendu avec des valeurs sentinelles, aucune n'apparaît."""
    with translation.override(language):
        subject = render_to_string(name, sentinel_context())
    assert "SENTINELLE" not in subject
    assert "@" not in subject
    assert "\n" not in subject.strip()


def test_context_whitelist_is_the_plan_list():
    """§8.3 : contexte réduit à des chaînes ; toute nouvelle clé se justifie en revue."""
    assert {
        "activate_url",
        "password_reset_url",
        "signup_url",
        "site_name",
        "display_name",
        "timestamp",
        "ip",
        "user_agent",
    } == ALLOWED_CONTEXT_KEYS


def test_project_templates_only_use_whitelisted_variables():
    """Les gabarits d'e-mails n'accèdent à aucun attribut d'objet (« user.password »…)."""
    import re

    variable = re.compile(r"{{\s*([a-zA-Z_][\w.]*)")
    allowed = ALLOWED_CONTEXT_KEYS | {"LANGUAGE_CODE"}
    for templates_dir in APPS_DIR.glob("*/templates"):
        for path in templates_dir.rglob("*/email/*"):
            used = set(variable.findall(path.read_text(encoding="utf-8")))
            assert used <= allowed, (path, used - allowed)
            assert not any("." in name for name in used), path
