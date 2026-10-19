"""Chargement d'une édition réelle depuis un dossier versionné (décision T3, ``load_edition``).

Les tests chargent le vrai dossier ``data/editions/icha-2027`` (affiche de la conférence
internationale sur l'analyse harmonique 2027) : ce qui est versionné est ce qui est testé.
"""

import json
import shutil
from io import StringIO
from pathlib import Path

import pytest
from allauth.account.models import EmailAddress
from django.core.management import CommandError, call_command

from apps.accounts.models import RoleInvitation, User, UserRole
from apps.accounts.roles import Role
from apps.conferences.loader import EditionDataError, load_edition, read_edition_data
from apps.conferences.models import Conference, Edition, KeyDate
from apps.conferences.services import current_public_edition
from apps.core.models import AuditLog, PublicFile
from apps.portal.models import PageSection, Section
from apps.registrations.models import Fee, RegistrationSettings
from apps.sponsors.models import Sponsor

pytestmark = pytest.mark.django_db

ICHA = Path(__file__).resolve().parents[3] / "data" / "editions" / "icha-2027"


def test_t3_icha_2027_data_file_is_valid():
    data = read_edition_data(ICHA)
    assert data["edition"]["code"] == "ICHA2027"
    assert data["edition"]["double_blind"] is False


def test_t3_load_edition_creates_the_published_current_edition():
    report = load_edition(ICHA)
    edition = Edition.objects.get(code="ICHA2027")
    assert report.conference_created
    assert edition.status == "published"
    assert edition.conference.current_edition_id == edition.pk
    assert current_public_edition() == edition
    assert (edition.start_date.isoformat(), edition.end_date.isoformat()) == (
        "2027-05-31",
        "2027-06-04",
    )
    assert edition.double_blind is False
    assert edition.submission_languages == ["en", "fr"]
    assert list(edition.tracks.order_by("position").values_list("code", flat=True)) == [
        "edp",
        "geometrie",
        "probabilites",
        "applications",
    ]
    assert set(edition.submission_types.values_list("code", flat=True)) == {
        "oral",
        "forum-doctoral",
    }
    codes = set(KeyDate.objects.filter(edition=edition).values_list("code", flat=True))
    assert codes == {"call_open", "call_close"}
    # Tout passe par les services : chaque création est journalisée (RG-17).
    assert AuditLog.objects.filter(action="edition.created", edition=edition).exists()


def test_t3_registration_uses_one_currency_and_free_international_fees():
    load_edition(ICHA)
    edition = Edition.objects.get(code="ICHA2027")
    assert RegistrationSettings.objects.get(edition=edition).currency == "XOF"
    fees = {
        (fee.category.code, fee.period, fee.zone): fee.amount
        for fee in Fee.objects.filter(category__edition=edition)
    }
    assert fees[("etudiant", "regular", "local")] == 20000
    assert fees[("enseignant", "regular", "local")] == 50000
    assert fees[("enseignant", "onsite", "international")] == 0


def test_t3_portal_poster_sponsors_and_sections():
    load_edition(ICHA)
    edition = Edition.objects.get(code="ICHA2027")
    assert edition.poster is not None and edition.poster.published
    assert PublicFile.objects.filter(edition=edition, kind="document", published=True).count() == 1
    sponsors = Sponsor.objects.filter(edition=edition)
    assert sponsors.count() == 6
    assert all(sponsor.published and sponsor.logo_id for sponsor in sponsors)
    placed = {
        (row.page.slug, row.section.code)
        for row in PageSection.objects.filter(page__edition=edition).select_related(
            "page", "section"
        )
    }
    assert ("home", "presentation") in placed
    assert ("home", "parrainage") in placed
    assert ("home", "tracks") in placed
    assert ("committees", "composition-comites") in placed
    assert ("registration", "tarifs") in placed
    patron = Section.objects.get(edition=edition, code="parrainage")
    assert patron.image is not None and patron.image.kind == "image"


def test_t3_public_portal_serves_the_loaded_edition(api_client):
    load_edition(ICHA)
    response = api_client.get("/v1/public/portal/site")
    assert response.status_code == 200
    body = json.dumps(response.json(), ensure_ascii=False)
    assert "analyse harmonique" in body.lower()


def test_t3_load_edition_refuses_an_existing_edition_and_writes_nothing_more():
    load_edition(ICHA)
    count = Edition.objects.count()
    with pytest.raises(EditionDataError):
        load_edition(ICHA)
    assert Edition.objects.count() == count


def test_t3_load_edition_is_all_or_nothing(tmp_path):
    broken = tmp_path / "icha"
    shutil.copytree(ICHA, broken)
    data = json.loads((broken / "edition.json").read_text(encoding="utf-8"))
    data["sections"].append({"page": "home", "code": "inexistante", "seeded": True})
    (broken / "edition.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Section.DoesNotExist):
        load_edition(broken)
    assert not Edition.objects.filter(code="ICHA2027").exists()
    assert not Conference.objects.filter(slug="icha").exists()


def test_t3_unknown_edition_field_or_missing_file_is_refused(tmp_path):
    broken = tmp_path / "icha"
    shutil.copytree(ICHA, broken)
    data = json.loads((broken / "edition.json").read_text(encoding="utf-8"))
    data["edition"]["status"] = "published"
    (broken / "edition.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EditionDataError, match="status"):
        read_edition_data(broken)
    data["edition"].pop("status")
    data["files"]["poster_image"]["path"] = "../../secret.png"
    (broken / "edition.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(EditionDataError, match="hors du dossier"):
        read_edition_data(broken)


def test_t3_draft_option_keeps_the_edition_private():
    load_edition(ICHA, publish=False)
    edition = Edition.objects.get(code="ICHA2027")
    assert edition.status == "draft"
    assert edition.conference.current_edition_id is None


def test_t3_admin_email_invites_or_grants_admin_without_global_role():
    load_edition(ICHA, admin_email="Responsable@Exemple.org")
    edition = Edition.objects.get(code="ICHA2027")
    assert RoleInvitation.objects.filter(
        edition=edition, email="responsable@exemple.org", role=Role.ADMIN
    ).exists()
    assert not UserRole.objects.filter(edition=edition).exists()


def test_t3_admin_email_grants_admin_to_a_verified_account():
    user = User.objects.create(email="admin@exemple.org")
    EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
    load_edition(ICHA, admin_email="admin@exemple.org")
    edition = Edition.objects.get(code="ICHA2027")
    assert UserRole.objects.filter(user=user, edition=edition, role=Role.ADMIN).exists()


def test_t3_load_edition_command_reports_and_refuses_twice():
    out = StringIO()
    call_command("load_edition", str(ICHA), stdout=out)
    assert "ICHA2027 chargée (publiée et courante)" in out.getvalue()
    with pytest.raises(CommandError, match="existe déjà"):
        call_command("load_edition", str(ICHA), stdout=StringIO())


def test_t3_loaded_edition_takes_the_portal_once_the_demo_is_back_to_draft():
    """Sur l'hébergement, l'édition DEMO (conférence fictive, créée avant) occupe le portail :
    repassée en brouillon par l'opérateur, elle laisse la place à l'édition chargée."""
    from apps.conferences.services import set_edition_status
    from apps.core.actor import Actor
    from apps.qa.demo import seed_demo

    seed_demo()
    load_edition(ICHA)
    demo = Edition.objects.get(code="DEMO")
    assert current_public_edition() == demo
    set_edition_status(
        demo, "draft", actor=Actor.command("cli:set_edition_status"), reason="Retrait du portail"
    )
    assert current_public_edition() == Edition.objects.get(code="ICHA2027")
