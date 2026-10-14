"""Édition de démonstration pour la recette et la formation (plan L9, S10 et S11).

L'édition ``DEMO`` de la conférence fictive : publiée et courante (le portail la sert), appel
ouvert, évaluation et version finale datées, inscriptions ouvertes (virement et sur place ;
paiement en ligne si un fournisseur est configuré), deux thématiques, un type de
communication, grille par défaut, une catégorie tarifaire, mentions de facturation, deux
salles. Un compte fictif par rôle (``<nom>@fictif.invalid`` : aucun e-mail ne leur parvient),
mot de passe et secret TOTP communs tirés au hasard, affichés une seule fois.

Tout passe par les services métier, comme un opérateur le ferait ; la recette joue ensuite
les démos A à I (``docs/L9-cahier-de-recette.md``) dans les écrans.
"""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import encrypt
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile, RoleSource, User
from apps.accounts.roles import MFA_REQUIRED_ROLES, OcFunction, Role
from apps.accounts.services.roles import grant_role
from apps.conferences import services as conferences
from apps.conferences.models import Conference, Edition
from apps.core.actor import Actor
from apps.qa.fictitious import FICTITIOUS_CONFERENCE, fictitious_email

DEMO_EDITION = "DEMO"
ZONE = "Africa/Abidjan"

# (nom du compte, prénom, nom, institution, pays, rôle, fonction au CO)
ACCOUNTS: tuple[tuple[str, str, str, str, str, str | None, str], ...] = (
    ("admin", "Aya", "Konan", "Université fictive", "CI", Role.ADMIN, ""),
    ("presidence", "Yao", "Kouassi", "Université fictive", "CI", Role.CHAIR, ""),
    ("president.cs", "Koffi", "Yao", "Institut fictif", "CI", Role.SC_CHAIR, ""),
    ("relecteur1", "Aminata", "Diallo", "Centre fictif R1", "SN", Role.SC_MEMBER, ""),
    ("relecteur2", "Serge", "Ekra", "Centre fictif R2", "CI", Role.SC_MEMBER, ""),
    ("relecteur3", "Claire", "Martin", "Centre fictif R3", "FR", Role.SC_MEMBER, ""),
    ("co.programme", "Mariam", "Bamba", "Université fictive", "CI", Role.OC_MEMBER, "program"),
    ("co.finances", "Fatou", "Sangaré", "Université fictive", "CI", Role.OC_MEMBER, "finance"),
    (
        "co.secretariat",
        "Adjoua",
        "Kouamé",
        "Université fictive",
        "CI",
        Role.OC_MEMBER,
        OcFunction.SECRETARIAT,
    ),
    (
        "co.logistique",
        "Kader",
        "Ouattara",
        "Université fictive",
        "CI",
        Role.OC_MEMBER,
        OcFunction.LOGISTICS,
    ),
    (
        "co.communication",
        "Nadia",
        "Koffi",
        "Université fictive",
        "CI",
        Role.OC_MEMBER,
        OcFunction.COMMUNICATION,
    ),
    (
        "co.relations",
        "Paul",
        "Aka",
        "Université fictive",
        "CI",
        Role.OC_MEMBER,
        OcFunction.EXTERNAL_RELATIONS,
    ),
    (
        "co.benevoles",
        "Rokia",
        "Coulibaly",
        "Université fictive",
        "CI",
        Role.OC_MEMBER,
        OcFunction.VOLUNTEERS,
    ),
    ("benevole", "Ali", "Touré", "Université fictive", "CI", Role.VOLUNTEER, ""),
    ("signataire", "Brou", "Assi", "Université fictive", "CI", Role.SIGNATORY, ""),
    ("intervenant", "Ama", "Owusu", "Université fictive du Ghana", "GH", Role.SPEAKER, ""),
    ("auteur1", "Awa", "Koné", "Université fictive A", "CI", None, ""),
    ("auteur2", "Moussa", "Traoré", "Université fictive B", "ML", None, ""),
    ("participant1", "Ousmane", "Ndiaye", "Université fictive C", "SN", None, ""),
    ("participant2", "Léa", "Dubois", "Université fictive D", "FR", None, ""),
)


@dataclass
class DemoReport:
    password: str
    totp_secret: str
    edition: int = 0
    accounts: list[tuple[str, str]] = field(default_factory=list)


def _base32_secret() -> str:
    import base64

    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def _local_now() -> dt.datetime:
    return timezone.localtime(timezone.now(), ZoneInfo(ZONE)).replace(tzinfo=None, microsecond=0)


def demo_exists() -> bool:
    return Edition.objects.filter(
        conference__slug=FICTITIOUS_CONFERENCE, code=DEMO_EDITION
    ).exists()


def fictitious_conference(actor: Actor) -> Conference:
    """Conférence fictive partagée par la démonstration et les données de volume."""
    found = Conference.objects.filter(slug=FICTITIOUS_CONFERENCE).first()
    if found is not None:
        return found
    return conferences.create_conference(
        slug=FICTITIOUS_CONFERENCE,
        name_fr="Conférence fictive (recette et charge)",
        name_en="Fictitious conference (acceptance and load)",
        actor=actor,
    )


@transaction.atomic
def seed_demo() -> DemoReport:
    from apps.payments.services.billing import update_billing_profile
    from apps.program.services import planning
    from apps.registrations.services import pricing
    from apps.registrations.services.settings import update_registration_settings
    from apps.reviews.services.grids import create_grid

    actor = Actor.command("cli:seed_demo")
    report = DemoReport(password=secrets.token_urlsafe(18), totp_secret=_base32_secret())
    conference = fictitious_conference(actor)
    today = timezone.localdate()
    edition = conferences.create_edition(
        conference=conference,
        actor=actor,
        code=DEMO_EDITION,
        slug="demo",
        year=today.year + 1,
        title_fr="Édition de démonstration",
        title_en="Demonstration edition",
        timezone=ZONE,
        start_date=today + dt.timedelta(days=90),
        end_date=today + dt.timedelta(days=92),
    )
    report.edition = edition.pk
    for code, name_fr, name_en in (
        ("ia", "Intelligence artificielle", "Artificial intelligence"),
        ("sante", "Santé publique", "Public health"),
    ):
        conferences.create_track(
            edition, {"code": code, "name_fr": name_fr, "name_en": name_en}, actor=actor
        )
    conferences.create_submission_type(
        edition,
        {
            "code": "oral",
            "label_fr": "Communication orale",
            "label_en": "Oral paper",
            "file_policy": "optional",
            "max_file_mb": 10,
        },
        actor=actor,
    )
    now = _local_now()
    for code, days in (
        ("call_open", -1),
        ("call_close", 30),
        ("review_deadline", 50),
        ("camera_ready", 70),
        ("registration_open", -1),
        ("early_bird_end", 20),
        ("registration_close", 85),
    ):
        conferences.create_key_date(
            edition, {"code": code, "at_local": now + dt.timedelta(days=days)}, actor=actor
        )
    create_grid(edition, name="Grille de démonstration", actor=actor)
    conferences.set_edition_status(edition, "published", actor=actor, reason="Démonstration")
    edition.refresh_from_db()
    conferences.set_current_edition(conference, edition, actor=actor)

    update_registration_settings(
        edition,
        {
            "online_enabled": bool(settings.GESTCONF_PAYMENT_PROVIDER),
            "transfer_enabled": True,
            "onsite_enabled": True,
            "local_countries": ["CI"],
        },
        actor=actor,
    )
    update_billing_profile(
        edition,
        {"legal_name": "Organisateur fictif", "address": "Adresse fictive, Abidjan"},
        actor=actor,
    )
    category = pricing.create_category(
        edition,
        {"code": "chercheur", "label_fr": "Chercheur", "label_en": "Researcher", "position": 0},
        actor=actor,
    )
    pricing.set_fees(
        category,
        [
            {"period": period, "zone": zone, "amount": Decimal(amount)}
            for period, zone, amount in (
                ("early", "local", "40000"),
                ("early", "international", "100000"),
                ("regular", "local", "50000"),
                ("regular", "international", "120000"),
            )
        ],
        actor=actor,
    )
    for name in ("Amphithéâtre A", "Salle B"):
        planning.create_room(edition, {"name": name}, actor=actor)

    password_hash = make_password(report.password)
    for name, first, last, institution, country, role, oc_function in ACCOUNTS:
        email = fictitious_email(name)
        user = User.objects.create(email=email, password=password_hash)
        EmailAddress.objects.create(user=user, email=email, primary=True, verified=True)
        Profile.objects.update_or_create(
            user=user,
            defaults={
                "first_name": first,
                "last_name": last,
                "institution": institution,
                "country": country,
            },
        )
        # 2FA activée pour les rôles de gestion (optionnelle mais recommandée, T1) : la
        # recette joue la connexion en deux étapes, le portail permet de la désactiver.
        if role in MFA_REQUIRED_ROLES:
            Authenticator.objects.create(
                user=user,
                type=Authenticator.Type.TOTP,
                data={"secret": encrypt(report.totp_secret)},
            )
        if role is not None:
            grant_role(
                user=user,
                edition=edition,
                role=role,
                actor=actor,
                source=RoleSource.COMMAND,
                oc_function=str(oc_function),
            )
        report.accounts.append((email, str(Role(role).label) if role else "sans rôle"))
    return report
