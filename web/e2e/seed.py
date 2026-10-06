"""Données du parcours de bout en bout (plan L3, F14 ; plan L4 §7), créées par les services
comme un opérateur le ferait : conférence, édition publiée et courante, appel ouvert,
thématique, type à PDF obligatoire ; PDF de test porteur de métadonnées (retirées en double
aveugle). Pour l'évaluation (L4) : grille par défaut, fin des évaluations et date de la
version finale, président du comité scientifique et deux relecteurs (rôles attribués par
commande, 2FA TOTP activée avec un secret de test connu du navigateur).

Lu sur l'entrée standard de ``manage.py shell`` par ``e2e/django.ts`` ; imprime du JSON.
"""

import datetime as dt
import json
import tempfile
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import encrypt
from django.utils import timezone
from pypdf import PdfWriter

from apps.accounts.models import Profile, Role, RoleSource, User
from apps.accounts.services.roles import grant_role
from apps.conferences import services as conferences
from apps.core.actor import Actor
from apps.reviews.services.grids import create_grid

actor = Actor.command("cli:e2e")
zone = "Africa/Abidjan"
conference = conferences.create_conference(
    slug="gestconf-e2e", name_fr="Colloque E2E", name_en="E2E Conference", actor=actor
)
edition = conferences.create_edition(
    conference=conference,
    actor=actor,
    code="E2E27",
    slug="e2e27",
    year=2027,
    title_fr="Colloque E2E 2027",
    title_en="E2E Conference 2027",
    timezone=zone,
    start_date=dt.date(2027, 3, 1),
    end_date=dt.date(2027, 3, 3),
)
conferences.create_track(
    edition,
    {"code": "ia", "name_fr": "Intelligence artificielle", "name_en": "AI"},
    actor=actor,
)
conferences.create_submission_type(
    edition,
    {
        "code": "oral",
        "label_fr": "Communication orale",
        "label_en": "Oral paper",
        "file_policy": "required",
        "max_file_mb": 5,
    },
    actor=actor,
)
now = timezone.localtime(timezone.now(), ZoneInfo(zone)).replace(tzinfo=None, microsecond=0)
conferences.create_key_date(
    edition, {"code": "call_open", "at_local": now - dt.timedelta(days=1)}, actor=actor
)
conferences.create_key_date(
    edition,
    {"code": "call_close", "at_local": now + dt.timedelta(days=10)},
    actor=actor,
)
conferences.create_key_date(
    edition,
    {"code": "review_deadline", "at_local": now + dt.timedelta(days=20)},
    actor=actor,
)
conferences.create_key_date(
    edition,
    {"code": "camera_ready", "at_local": now + dt.timedelta(days=40)},
    actor=actor,
)
create_grid(edition, name="Grille E2E", actor=actor)
conferences.set_edition_status(edition, "published", actor=actor, reason="E2E")
conferences.set_current_edition(conference, edition, actor=actor)

writer = PdfWriter()
writer.add_blank_page(595, 842)
writer.add_metadata({"/Author": "Awa Koné", "/Title": "Article de test"})
with tempfile.NamedTemporaryFile(prefix="gestconf-e2e-", suffix=".pdf", delete=False) as handle:
    writer.write(handle)

# Comité scientifique : comptes vérifiés, profils complets, 2FA (imposée aux rôles SC_*).
# Identifiants de test, connus du navigateur de test, sur une base jetable : pas des secrets.
PASSWORD = "Une-phrase-assez-longue-2026"  # noqa: S105
TOTP_SECRET = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"  # noqa: S105
# Programme (plan L5) : CO de fonction « programme » (écriture) et Chair (publication, I1).
committee = {
    "chair": ("president.cs@e2e.example.org", "Koffi", "Yao", "Institut Pasteur", Role.SC_CHAIR),
    "program": (
        "programme@e2e.example.org",
        "Mariam",
        "Bamba",
        "INP-HB",
        Role.OC_MEMBER,
    ),
    "conference_chair": (
        "president@e2e.example.org",
        "Yao",
        "Kouassi",
        "Université FHB",
        Role.CHAIR,
    ),
    "reviewer1": (
        "relecteur.un@e2e.example.org",
        "Aminata",
        "Diallo",
        "Université Cheikh Anta Diop",
        Role.SC_MEMBER,
    ),
    "reviewer2": (
        "relecteur.deux@e2e.example.org",
        "Serge",
        "Ekra",
        "Université Nangui Abrogoua",
        Role.SC_MEMBER,
    ),
}
for email, first_name, last_name, institution, role in committee.values():
    user = User.objects.create_user(email=email, password=PASSWORD)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
    Profile.objects.update_or_create(
        user=user,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "institution": institution,
            "country": "CI",
        },
    )
    Authenticator.objects.create(
        user=user, type=Authenticator.Type.TOTP, data={"secret": encrypt(TOTP_SECRET)}
    )
    grant_role(
        user=user,
        edition=edition,
        role=role,
        actor=actor,
        source=RoleSource.COMMAND,
        oc_function="program" if role == Role.OC_MEMBER else "",
    )

print(
    json.dumps(
        {
            "code": edition.code,
            "edition": edition.pk,
            "pdf": handle.name,
            "password": PASSWORD,
            "totp": TOTP_SECRET,
            **{key: value[0] for key, value in committee.items()},
        }
    )
)
