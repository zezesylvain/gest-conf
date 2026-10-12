"""Données de volume pour le test de charge (plan L9, S6 ; étude §12).

Deux éditions d'une conférence fictive, au volume de l'étude par défaut :

- ``FICTIFEVAL`` : appel clos, soumissions en évaluation (relecteurs affectés, une partie des
  évaluations envoyées) : listes du comité, espace du relecteur ;
- ``FICTIFAPPEL`` : appel ouvert (brouillons des auteurs, pic de clôture) et inscriptions
  ouvertes (participants inscrits, la plupart payés par virement enregistré).

Tout passe par les services métier : les statuts sont écrits par les workflows (règle n° 4),
les règles de gestion s'appliquent. Seuls les comptes sont créés en masse, avec un seul
hachage de mot de passe (le hachage PBKDF2 d'un million d'itérations coûterait sinon des
dizaines de minutes) ; le mot de passe et le secret TOTP sont tirés au hasard et affichés une
seule fois.
"""

from __future__ import annotations

import datetime as dt
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import cycle
from zoneinfo import ZoneInfo

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import encrypt
from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Profile, RoleSource, User
from apps.accounts.roles import Role
from apps.accounts.services.roles import grant_role
from apps.conferences import services as conferences
from apps.conferences.models import Conference, Edition, KeyDate
from apps.core.actor import Actor, ActorKind
from apps.qa.fictitious import FICTITIOUS_CONFERENCE, fictitious_email

ZONE = "Africa/Abidjan"
COUNTRIES = ("CI", "SN", "BF", "ML", "CM", "FR", "BE", "CA")
INSTITUTIONS = (
    "Université fictive A",
    "Université fictive B",
    "Institut fictif C",
    "École fictive D",
)
# Relecteurs : institutions distinctes de celles des auteurs (aucun conflit d'institution).
REVIEWER_INSTITUTIONS = ("Centre fictif R1", "Centre fictif R2", "Centre fictif R3")
DECLARATIONS = {"originality": True, "ethics": True, "conflicts": True, "publication": True}


@dataclass
class VolumeReport:
    password: str
    totp_secret: str
    editions: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    committee: dict[str, str] = field(default_factory=dict)


def _as(user: User) -> Actor:
    """Acteur « utilisateur » : la personne fictive agit elle-même, comme par l'API."""
    return Actor(kind=ActorKind.USER, user=user)


def _local_now() -> dt.datetime:
    return timezone.localtime(timezone.now(), ZoneInfo(ZONE)).replace(tzinfo=None, microsecond=0)


def _users(prefix: str, count: int, password_hash: str, institutions: tuple[str, ...]) -> list:
    """Comptes fictifs vérifiés, profil complet, en masse (même hachage pour tous)."""
    users = User.objects.bulk_create(
        [
            User(email=fictitious_email(f"{prefix}{index:04d}"), password=password_hash)
            for index in range(1, count + 1)
        ]
    )
    users = list(User.objects.filter(email__in=[user.email for user in users]).order_by("id"))
    EmailAddress.objects.bulk_create(
        [EmailAddress(user=user, email=user.email, primary=True, verified=True) for user in users]
    )
    Profile.objects.bulk_create(
        [
            Profile(
                user=user,
                first_name=f"{prefix.capitalize()}{index}",
                last_name="Fictif",
                institution=institutions[index % len(institutions)],
                country=COUNTRIES[index % len(COUNTRIES)],
            )
            for index, user in enumerate(users, 1)
        ]
    )
    return users


def _with_totp(users: list, secret: str) -> None:
    Authenticator.objects.bulk_create(
        [
            Authenticator(user=user, type=Authenticator.Type.TOTP, data={"secret": encrypt(secret)})
            for user in users
        ]
    )


def _grant(users: list, edition: Edition, role: str, actor: Actor, oc_function: str = "") -> None:
    for user in users:
        grant_role(
            user=user,
            edition=edition,
            role=role,
            actor=actor,
            source=RoleSource.COMMAND,
            oc_function=oc_function,
        )


def _edition(conference: Conference, code: str, title: str, actor: Actor) -> Edition:
    today = timezone.localdate()
    edition = conferences.create_edition(
        conference=conference,
        actor=actor,
        code=code,
        slug=code.lower(),
        year=today.year + 1,
        title_fr=f"{title} (fictive)",
        title_en=f"{title} (fictitious)",
        timezone=ZONE,
        start_date=today + dt.timedelta(days=90),
        end_date=today + dt.timedelta(days=92),
        reviewers_per_submission=2,
        max_reviews_per_reviewer=30,
    )
    for track in ("ia", "sante", "energie", "education"):
        conferences.create_track(
            edition, {"code": track, "name_fr": track.capitalize(), "name_en": track}, actor=actor
        )
    conferences.create_submission_type(
        edition,
        {
            "code": "oral",
            "label_fr": "Communication orale",
            "label_en": "Oral paper",
            "file_policy": "optional",
        },
        actor=actor,
    )
    return edition


def _key_dates(edition: Edition, dates: dict[str, dt.datetime], actor: Actor) -> None:
    for code, at_local in dates.items():
        conferences.create_key_date(edition, {"code": code, "at_local": at_local}, actor=actor)


def _publish(edition: Edition, actor: Actor) -> None:
    from apps.reviews.services.grids import create_grid

    create_grid(edition, name="Grille fictive", actor=actor)
    conferences.set_edition_status(edition, "published", actor=actor, reason="Données fictives")
    edition.refresh_from_db()


def _draft(edition: Edition, author: User, index: int, *, complete: bool):
    from apps.submissions import services as submissions

    actor = _as(author)
    submission = submissions.create_draft(edition, actor=actor)
    tracks = list(edition.tracks.order_by("id"))
    data = {
        "title": f"Communication fictive n° {index} sur un sujet de recherche",
        "abstract": "Résumé fictif destiné au test de charge. " * 20,
        "keywords": ["fictif", "charge", f"sujet{index % 10}"],
        "track": tracks[index % len(tracks)],
        "submission_type": edition.submission_types.first(),
        "language": "fr",
    }
    if complete:
        data["declarations"] = DECLARATIONS
    return submissions.update_submission(submission, data, actor=actor)


def _progress(report: Callable[[str], None] | None, message: str) -> None:
    if report is not None:
        report(message)


def seed_volume(
    *,
    submissions: int = 600,
    reviewers: int = 100,
    participants: int = 1500,
    drafts: int = 300,
    progress: Callable[[str], None] | None = None,
) -> VolumeReport:
    """Crée la conférence fictive et ses deux éditions (garde-fous : ``fictitious``)."""
    from apps.payments.services.billing import update_billing_profile
    from apps.payments.services.manual import record_manual_payment
    from apps.registrations.services import orders, pricing
    from apps.registrations.services.settings import update_registration_settings
    from apps.reviews.services import assignments, reviews
    from apps.submissions import workflow
    from apps.submissions.services import close_calls

    actor = Actor.command("cli:seed_volume")
    report = VolumeReport(password=secrets.token_urlsafe(18), totp_secret=_base32_secret())
    password_hash = make_password(report.password)
    with transaction.atomic():
        conference = conferences.create_conference(
            slug=FICTITIOUS_CONFERENCE,
            name_fr="Conférence fictive (recette et charge)",
            name_en="Fictitious conference (acceptance and load)",
            actor=actor,
        )
        evaluation = _edition(conference, "FICTIFEVAL", "Édition en évaluation", actor)
        call = _edition(conference, "FICTIFAPPEL", "Édition en appel", actor)
        report.editions = {"evaluation": evaluation.pk, "call": call.pk}
        now = _local_now()
        _key_dates(
            evaluation,
            {
                "call_open": now - dt.timedelta(days=2),
                "call_close": now + dt.timedelta(days=1),
                "review_deadline": now + dt.timedelta(days=20),
            },
            actor,
        )
        _key_dates(
            call,
            {
                "call_open": now - dt.timedelta(days=1),
                "call_close": now + dt.timedelta(days=30),
                "review_deadline": now + dt.timedelta(days=50),
                "registration_open": now - dt.timedelta(days=1),
                "early_bird_end": now + dt.timedelta(days=10),
                "registration_close": now + dt.timedelta(days=40),
            },
            actor,
        )
        _publish(evaluation, actor)
        _publish(call, actor)
        # Édition servie par l'API publique (devis, inscription, bandeau) pendant le test.
        conferences.set_current_edition(conference, call, actor=actor)

    _progress(progress, "comptes fictifs")
    authors = _users("auteur", submissions + drafts, password_hash, INSTITUTIONS)
    referees = _users("relecteur", reviewers, password_hash, REVIEWER_INSTITUTIONS)
    people = _users("participant", participants, password_hash, INSTITUTIONS)
    chair, finance = _users("comite", 2, password_hash, INSTITUTIONS)
    _with_totp([*referees, chair, finance], report.totp_secret)
    _grant(referees, evaluation, Role.SC_MEMBER, actor)
    _grant([chair], evaluation, Role.SC_CHAIR, actor)
    _grant([finance], call, Role.OC_MEMBER, actor, oc_function="finance")
    report.committee = {"sc_chair": chair.email, "oc_finance": finance.email}

    _progress(progress, f"{submissions} soumissions envoyées")
    sent = []
    for index, author in enumerate(authors[:submissions], 1):
        draft = _draft(evaluation, author, index, complete=True)
        sent.append(workflow.transition(draft, "submitted", _as(author)))

    _progress(progress, "clôture de l'appel, recevabilité, affectations")
    closing = KeyDate.objects.get(edition=evaluation, code="call_close")
    conferences.update_key_date(
        closing, {"at_local": _local_now() - dt.timedelta(minutes=1)}, actor=actor
    )
    close_calls(actor=actor)
    chair_actor = _as(chair)
    pool = cycle(referees)
    assigned = []
    for submission in sent:
        for _ in range(evaluation.reviewers_per_submission):
            assigned.append(assignments.assign(submission, next(pool), actor=chair_actor))
        assignments.screen(submission, admissible=True, reason="", actor=chair_actor)

    _progress(progress, "évaluations envoyées (deux sur trois)")
    criteria = [criterion.code for criterion in _grid_criteria(evaluation)]
    reviewed = 0
    for rank, assignment in enumerate(assigned):
        if rank % 3 == 2:
            continue
        data = {
            "scores": {code: Decimal(1 + (rank + n) % 5) for n, code in enumerate(criteria)},
            "recommendation": ("accept", "accept_minor", "reject", "discuss")[rank % 4],
            "confidence": 1 + rank % 5,
            "comment_to_authors": "Commentaire fictif aux auteurs.",
        }
        reviews.submit_review(assignment, data, actor=_as(assignment.reviewer))
        reviewed += 1

    _progress(progress, f"{drafts} brouillons (appel ouvert)")
    for index, author in enumerate(authors[submissions:], 1):
        _draft(call, author, index, complete=index % 2 == 0)

    _progress(progress, f"{participants} inscriptions")
    update_registration_settings(
        call,
        {"transfer_enabled": True, "local_countries": ["CI"]},
        actor=actor,
    )
    # Mentions de facturation : sans elles, aucune facture n'est émise au paiement (RG-14).
    update_billing_profile(
        call,
        {"legal_name": "Organisateur fictif", "address": "Adresse fictive, Abidjan"},
        actor=actor,
    )
    category = pricing.create_category(
        call,
        {"code": "chercheur", "label_fr": "Chercheur", "label_en": "Researcher", "position": 0},
        actor=actor,
    )
    pricing.set_fees(
        category,
        [
            {"period": period, "zone": zone, "amount": Decimal(amount)}
            for period in ("early", "regular")
            for zone, amount in (("local", "50000"), ("international", "120000"))
        ],
        actor=actor,
    )
    paid = 0
    for index, person in enumerate(people):
        registration = orders.place_order(
            call,
            person,
            category="chercheur",
            method="transfer",
            actor=_as(person),
        )
        if index % 3 != 2:
            record_manual_payment(
                registration,
                method="transfer",
                amount=registration.total,
                reference=f"VIR-FICTIF-{registration.pk}",
                received_on=timezone.localdate(),
                actor=_as(finance),
            )
            paid += 1

    report.counts = {
        "authors": len(authors),
        "reviewers": len(referees),
        "participants": len(people),
        "submissions": len(sent),
        "assignments": len(assigned),
        "reviews": reviewed,
        "drafts": drafts,
        "registrations": len(people),
        "paid": paid,
    }
    return report


def _grid_criteria(edition: Edition):
    from apps.reviews.models import EvaluationGrid

    grid = EvaluationGrid.objects.filter(edition=edition).order_by("-version").first()
    return grid.criteria.order_by("position")


def _base32_secret() -> str:
    """Secret TOTP de 160 bits en base32 (RFC 4226), comme ceux qu'allauth produit."""
    import base64

    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")
