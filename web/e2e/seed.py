"""Données du parcours de bout en bout (plan L3, F14 ; plan L4 §7), créées par les services
comme un opérateur le ferait : conférence, édition publiée et courante, appel ouvert,
thématique, type à PDF obligatoire ; PDF de test porteur de métadonnées (retirées en double
aveugle). Pour l'évaluation (L4) : grille par défaut, fin des évaluations et date de la
version finale, président du comité scientifique et deux relecteurs (rôles attribués par
commande, 2FA TOTP activée avec un secret de test connu du navigateur). Pour les inscriptions
(L6) : dates d'inscription, paramètres (paiement en ligne par le fournisseur factice, virement,
sur place ; pays local : CI), une catégorie et sa grille, une option à quota ; CO de fonction
« finances » ; un second participant (Sénégal, tarif international) sans rôle. Pour le jour J
(L7) : un bénévole, un CO « secrétariat » et un signataire (2FA), et une image de signature.
Pour le lot L8 : CO « logistique », « communication » et « relations extérieures », et un
intervenant invité.

Lu sur l'entrée standard de ``manage.py shell`` par ``e2e/django.ts`` ; imprime du JSON.
"""

import datetime as dt
import json
import tempfile
from decimal import Decimal
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import encrypt
from django.utils import timezone
from PIL import Image, ImageDraw
from pypdf import PdfWriter

from apps.accounts.models import Profile, Role, RoleSource, User
from apps.accounts.services.roles import grant_role
from apps.conferences import services as conferences
from apps.core.actor import Actor
from apps.registrations.services import pricing
from apps.registrations.services.settings import update_registration_settings
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
# Inscriptions (plan L6) : ouvertes, tarif préférentiel encore cinq jours.
for code, delta in (("registration_open", -1), ("early_bird_end", 5), ("registration_close", 30)):
    conferences.create_key_date(
        edition, {"code": code, "at_local": now + dt.timedelta(days=delta)}, actor=actor
    )
create_grid(edition, name="Grille E2E", actor=actor)
conferences.set_edition_status(edition, "published", actor=actor, reason="E2E")
conferences.set_current_edition(conference, edition, actor=actor)
update_registration_settings(
    edition,
    {"online_enabled": True, "transfer_enabled": True, "local_countries": ["CI"]},
    actor=actor,
)
researcher = pricing.create_category(
    edition,
    {"code": "chercheur", "label_fr": "Chercheur", "label_en": "Researcher", "position": 0},
    actor=actor,
)
pricing.set_fees(
    researcher,
    [
        {"period": "early", "zone": "local", "amount": Decimal("40000")},
        {"period": "early", "zone": "international", "amount": Decimal("100000")},
        {"period": "regular", "zone": "local", "amount": Decimal("50000")},
        {"period": "regular", "zone": "international", "amount": Decimal("120000")},
    ],
    actor=actor,
)
pricing.create_option(
    edition,
    {
        "code": "diner",
        "label_fr": "Dîner de gala",
        "label_en": "Gala dinner",
        "price_local": Decimal("10000"),
        "price_international": Decimal("15000"),
        "quota": 50,
    },
    actor=actor,
)

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
    # Inscriptions (plan L6, J1) : CO « finances » (tarifs, facturation, paiements manuels).
    "finance": (
        "finances@e2e.example.org",
        "Fatou",
        "Sangaré",
        "Université FHB",
        Role.OC_MEMBER,
    ),
    # Jour J (plan L7, K1, K18) : bénévole (accueil), CO « secrétariat » (comptoir,
    # présences, attestations, lettres) et signataire.
    "volunteer": ("benevole@e2e.example.org", "Ali", "Touré", "Université FHB", Role.VOLUNTEER),
    "secretariat": (
        "secretariat@e2e.example.org",
        "Adjoua",
        "Kouamé",
        "Université FHB",
        Role.OC_MEMBER,
    ),
    "signatory": (
        "signataire@e2e.example.org",
        "Brou",
        "Assi",
        "Université FHB",
        Role.SIGNATORY,
    ),
    # Lot L8 : CO « logistique » (venues, repas, postes), « communication » (annonces,
    # questionnaires), « relations extérieures » (partenaires) ; intervenant invité.
    "logistics": (
        "logistique@e2e.example.org",
        "Kader",
        "Ouattara",
        "Université FHB",
        Role.OC_MEMBER,
    ),
    "communication": (
        "communication@e2e.example.org",
        "Nadia",
        "Koffi",
        "Université FHB",
        Role.OC_MEMBER,
    ),
    "relations": (
        "relations@e2e.example.org",
        "Paul",
        "Aka",
        "Université FHB",
        Role.OC_MEMBER,
    ),
    "speaker": (
        "intervenant@e2e.example.org",
        "Ama",
        "Owusu",
        "University of Ghana",
        Role.SPEAKER,
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
        oc_function={
            "programme@e2e.example.org": "program",
            "finances@e2e.example.org": "finance",
            "secretariat@e2e.example.org": "secretariat",
            "logistique@e2e.example.org": "logistics",
            "communication@e2e.example.org": "communication",
            "relations@e2e.example.org": "external_relations",
        }.get(email, ""),
    )

# Second participant (plan L6) : compte vérifié, profil complet au Sénégal, sans rôle.
PARTICIPANT = "participant@e2e.example.org"
participant = User.objects.create_user(email=PARTICIPANT, password=PASSWORD)
EmailAddress.objects.create(user=participant, email=PARTICIPANT, primary=True, verified=True)
Profile.objects.update_or_create(
    user=participant,
    defaults={
        "first_name": "Ousmane",
        "last_name": "Ndiaye",
        "institution": "Université Cheikh Anta Diop",
        "country": "SN",
    },
)

# Image de signature (plan L7, K18), déposée par le signataire dans la gestion.
signature_image = Image.new("RGB", (480, 160), "white")
pen = ImageDraw.Draw(signature_image)
pen.line([(30, 120), (120, 40), (200, 110), (300, 50), (440, 100)], fill="navy", width=6)
with tempfile.NamedTemporaryFile(prefix="gestconf-e2e-", suffix=".png", delete=False) as image:
    signature_image.save(image, format="PNG")

print(
    json.dumps(
        {
            "code": edition.code,
            "edition": edition.pk,
            "pdf": handle.name,
            "password": PASSWORD,
            "totp": TOTP_SECRET,
            "participant": PARTICIPANT,
            "signature": image.name,
            **{key: value[0] for key, value in committee.items()},
        }
    )
)
