"""Rapports (plan L8, N13 ; étude M16) : indicateurs par section, en lecture seule.

Chaque section s'ouvre à la capacité qui protège **déjà** ses données (pas de capacité
propre) et ne contient **aucune donnée nominative** : uniquement des décomptes, des taux,
des moyennes et des montants agrégés. Une section rend des **tableaux** (titre, colonnes,
lignes) dans la langue de la requête ; l'interface en tire ses barres, toujours doublées du
tableau (accessibilité), et les exports CSV, XLSX et PDF en reprennent les lignes.
"""

from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import Count, Q
from django.utils import translation
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from apps.accounts.roles import Capability as C
from apps.conferences.models import Edition

ZERO = Decimal("0")


@dataclass
class Table:
    key: str
    title: str
    columns: list[str]
    rows: list[list[Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Section:
    code: str
    label: Any
    capability: str
    compute: Callable[[Edition], list[Table]]
    position: int


def _english() -> bool:
    return (translation.get_language() or "fr").startswith("en")


def _label(fr: str, en: str) -> str:
    return en if _english() and en else fr


def _percent(part: int, whole: int) -> Decimal | None:
    if not whole:
        return None
    return (Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _country(code: str) -> str:
    return code or "—"


# --- Soumissions (submissions.read) -------------------------------------------------------


def submissions_section(edition: Edition) -> list[Table]:
    from apps.submissions.models import Submission, SubmissionAuthor, SubmissionStatus
    from apps.submissions.segments import ACCEPTED

    rows = Submission.objects.filter(edition=edition)
    status_counts = dict(
        rows.values_list("status").annotate(n=Count("id")).values_list("status", "n")
    )
    by_status = Table(
        "by_status",
        gettext("Soumissions par statut"),
        [gettext("Statut"), gettext("Nombre")],
        [
            [str(label), status_counts.get(value, 0)]
            for value, label in SubmissionStatus.choices
            if status_counts.get(value)
        ],
    )
    sent = rows.exclude(status__in=(SubmissionStatus.DRAFT, SubmissionStatus.WITHDRAWN))
    accepted = Q(status__in=ACCEPTED)

    def grouped(key: str, title: str, label_of: Callable[[dict], str], fields: tuple[str, ...]):
        data = (
            sent.values(*fields)
            .annotate(total=Count("id"), accepted=Count("id", filter=accepted))
            .order_by(*fields)
        )
        return Table(
            key,
            title,
            [gettext("Libellé"), gettext("Envoyées"), gettext("Acceptées"), gettext("Taux (%)")],
            [
                [
                    label_of(item),
                    item["total"],
                    item["accepted"],
                    _percent(item["accepted"], item["total"]),
                ]
                for item in data
            ],
        )

    by_track = grouped(
        "by_track",
        gettext("Par thématique"),
        lambda item: _label(item["track__name_fr"] or "—", item["track__name_en"]),
        ("track__name_fr", "track__name_en"),
    )
    by_type = grouped(
        "by_type",
        gettext("Par type de communication"),
        lambda item: _label(
            item["submission_type__label_fr"] or "—", item["submission_type__label_en"]
        ),
        ("submission_type__label_fr", "submission_type__label_en"),
    )
    # Pays : celui du premier auteur, figé dans la soumission.
    first_authors = SubmissionAuthor.objects.filter(submission__in=sent, position=1).values_list(
        "submission_id", "country"
    )
    country_of = dict(first_authors)
    totals: Counter[str] = Counter()
    accepted_by: Counter[str] = Counter()
    for submission_id, status in sent.values_list("id", "status"):
        country = _country(country_of.get(submission_id, ""))
        totals[country] += 1
        if status in ACCEPTED:
            accepted_by[country] += 1
    by_country = Table(
        "by_country",
        gettext("Par pays du premier auteur"),
        [gettext("Pays"), gettext("Envoyées"), gettext("Acceptées"), gettext("Taux (%)")],
        [
            [
                country,
                totals[country],
                accepted_by[country],
                _percent(accepted_by[country], totals[country]),
            ]
            for country in sorted(totals)
        ],
    )
    return [by_status, by_track, by_type, by_country]


# --- Relecture (reviews.manage) -----------------------------------------------------------


def reviews_section(edition: Edition) -> list[Table]:
    from django.utils import timezone

    from apps.reviews.models import AssignmentStatus, ReviewAssignment, ReviewStatus
    from apps.reviews.services.assignments import REVIEWABLE

    now = timezone.now()
    active = ReviewAssignment.objects.filter(
        submission__edition=edition, status=AssignmentStatus.ACTIVE
    ).select_related("submission__track", "review")
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"assigned": 0, "submitted": 0, "late": 0, "delays": []}
    )
    for assignment in active:
        track = assignment.submission.track
        label = _label(track.name_fr, track.name_en) if track else "—"
        for key in (gettext("Toutes thématiques"), label):
            bucket = groups[key]
            bucket["assigned"] += 1
            review = getattr(assignment, "review", None)
            if (
                review is not None
                and review.status == ReviewStatus.SUBMITTED
                and review.submitted_at
            ):
                bucket["submitted"] += 1
                bucket["delays"].append(
                    (review.submitted_at - assignment.assigned_at).total_seconds()
                )
            elif (
                assignment.due_at
                and assignment.due_at < now
                and assignment.submission.status in REVIEWABLE
            ):
                bucket["late"] += 1

    def days(delays: list[float]) -> Decimal | None:
        if not delays:
            return None
        return (Decimal(sum(delays)) / len(delays) / 86400).quantize(
            Decimal("0.1"), rounding=ROUND_HALF_UP
        )

    return [
        Table(
            "delays",
            gettext("Délais de relecture et retards"),
            [
                gettext("Thématique"),
                gettext("Affectations"),
                gettext("Évaluations envoyées"),
                gettext("En retard"),
                gettext("Délai moyen (jours)"),
            ],
            [
                [key, value["assigned"], value["submitted"], value["late"], days(value["delays"])]
                for key, value in groups.items()
            ],
        )
    ]


# --- Inscriptions (registrations.read) ------------------------------------------------------


def registrations_section(edition: Edition) -> list[Table]:
    from apps.registrations.models import Registration, RegistrationStatus, Zone

    rows = Registration.objects.filter(edition=edition)
    statuses = dict(rows.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
    by_status = Table(
        "by_status",
        gettext("Inscriptions par statut"),
        [gettext("Statut"), gettext("Nombre")],
        [[str(label), statuses.get(value, 0)] for value, label in RegistrationStatus.choices],
    )
    confirmed = rows.filter(status=RegistrationStatus.CONFIRMED)
    zone = ZoneInfo(edition.timezone)
    weeks: Counter[str] = Counter()
    for at in confirmed.exclude(confirmed_at__isnull=True).values_list("confirmed_at", flat=True):
        year, week, _day = at.astimezone(zone).isocalendar()
        weeks[f"{year}-S{week:02d}"] += 1
    by_week = Table(
        "by_week",
        gettext("Inscriptions confirmées par semaine"),
        [gettext("Semaine"), gettext("Confirmées")],
        [[week, weeks[week]] for week in sorted(weeks)],
    )
    categories = (
        confirmed.values("category__label_fr", "category__label_en")
        .annotate(n=Count("id"))
        .order_by("category__position", "category__label_fr")
    )
    by_category = Table(
        "by_category",
        gettext("Par catégorie"),
        [gettext("Catégorie"), gettext("Confirmées")],
        [
            [_label(item["category__label_fr"], item["category__label_en"]), item["n"]]
            for item in categories
        ],
    )
    zones = dict(confirmed.values_list("zone").annotate(n=Count("id")).values_list("zone", "n"))
    by_zone = Table(
        "by_zone",
        gettext("Par zone"),
        [gettext("Zone"), gettext("Confirmées")],
        [[str(label), zones.get(value, 0)] for value, label in Zone.choices if zones.get(value)],
    )
    countries = Counter(
        _country(code) for code in confirmed.values_list("user__profile__country", flat=True)
    )
    by_country = Table(
        "by_country",
        gettext("Par pays"),
        [gettext("Pays"), gettext("Confirmées")],
        [[country, countries[country]] for country in sorted(countries)],
    )
    return [by_status, by_week, by_category, by_zone, by_country]


# --- Recettes (finance.read) ----------------------------------------------------------------


def finance_section(edition: Edition) -> list[Table]:
    from apps.payments.services.finance import dashboard
    from apps.registrations.models import PaymentMethod

    data = dashboard(edition)
    currency = data["currency"]
    summary = Table(
        "summary",
        gettext("Recettes (%(currency)s)") % {"currency": currency},
        [gettext("Indicateur"), gettext("Montant")],
        [
            [gettext("Encaissé"), data["collected"]],
            [gettext("Remboursé"), data["refunded"]],
            [gettext("Net"), data["net"]],
            [gettext("En attente de paiement"), data["outstanding"]],
        ],
    )
    labels = dict(PaymentMethod.choices)
    by_method = Table(
        "by_method",
        gettext("Encaissements par moyen"),
        [gettext("Moyen"), gettext("Paiements"), gettext("Montant")],
        [
            [str(labels.get(row["method"], row["method"])), row["count"], row["amount"]]
            for row in data["by_method"]
        ],
    )
    by_category = Table(
        "by_category",
        gettext("Inscriptions confirmées par catégorie"),
        [gettext("Catégorie"), gettext("Confirmées"), gettext("Montant")],
        [
            [_label(row["label_fr"], row["label_en"]), row["confirmed"], row["amount"]]
            for row in data["by_category"]
        ],
    )
    return [summary, by_method, by_category]


# --- Présence (registrations.read) ----------------------------------------------------------


def attendance_section(edition: Edition) -> list[Table]:
    from apps.events.models import Checkin
    from apps.registrations.models import Registration, RegistrationStatus

    zone = ZoneInfo(edition.timezone)
    confirmed = Registration.objects.filter(
        edition=edition, status=RegistrationStatus.CONFIRMED
    ).count()
    active = Checkin.objects.filter(edition=edition, active_key__isnull=False)
    days: dict[dt.date, set[int]] = defaultdict(set)
    for registration_id, at in active.values_list("registration_id", "scanned_at"):
        days[at.astimezone(zone).date()].add(registration_id)
    by_day = Table(
        "by_day",
        gettext("Présence par jour"),
        [gettext("Jour"), gettext("Présents"), gettext("Inscrits confirmés"), gettext("Taux (%)")],
        [
            [day.isoformat(), len(people), confirmed, _percent(len(people), confirmed)]
            for day, people in sorted(days.items())
        ],
    )
    sessions = (
        active.filter(session__isnull=False)
        .values(
            "session__title_fr",
            "session__title_en",
            "session__starts_at",
            "session__room__capacity",
        )
        .annotate(n=Count("registration", distinct=True))
        .order_by("session__starts_at", "session__title_fr")
    )
    by_session = Table(
        "by_session",
        gettext("Entrées par session"),
        [
            gettext("Session"),
            gettext("Début"),
            gettext("Entrées"),
            gettext("Capacité de la salle"),
            gettext("Remplissage (%)"),
        ],
        [
            [
                _label(item["session__title_fr"], item["session__title_en"]),
                item["session__starts_at"].astimezone(zone).strftime("%Y-%m-%d %H:%M"),
                item["n"],
                item["session__room__capacity"],
                _percent(item["n"], item["session__room__capacity"] or 0),
            ]
            for item in sessions
        ],
    )
    return [by_day, by_session]


# --- Satisfaction (surveys.manage) ----------------------------------------------------------


def satisfaction_section(edition: Edition) -> list[Table]:
    from apps.surveys import services as surveys
    from apps.surveys.models import Survey, SurveyStatus

    overview = Table(
        "rates",
        gettext("Taux de réponse"),
        [gettext("Questionnaire"), gettext("Invités"), gettext("Réponses"), gettext("Taux (%)")],
    )
    ratings = Table(
        "ratings",
        gettext("Notes moyennes (à partir de 5 réponses)"),
        [
            gettext("Questionnaire"),
            gettext("Question"),
            gettext("Réponses"),
            gettext("Moyenne sur 5"),
        ],
    )
    for survey in Survey.objects.filter(edition=edition, status=SurveyStatus.PUBLISHED).order_by(
        "opens_at", "id"
    ):
        results = surveys.results(survey)
        title = _label(survey.title_fr, survey.title_en)
        overview.rows.append(
            [
                title,
                results["invited"],
                results["answered"],
                _percent(results["answered"], results["invited"]),
            ]
        )
        for question in results["questions"]:
            if question["average"] is not None:
                ratings.rows.append(
                    [
                        title,
                        _label(question["label_fr"], question["label_en"]),
                        question["answers"],
                        question["average"],
                    ]
                )
    return [overview, ratings]


# --- Budget (budget.read) et partenaires (sponsors.read) -------------------------------------


def budget_section(edition: Edition) -> list[Table]:
    from apps.logistics.models import BudgetCategory, BudgetKind
    from apps.logistics.services.budget import summary

    data = summary(edition)
    kinds = dict(BudgetKind.choices)
    categories = dict(BudgetCategory.choices)
    totals = Table(
        "totals",
        gettext("Budget (%(currency)s)") % {"currency": data["currency"]},
        [gettext("Nature"), gettext("Prévu"), gettext("Réalisé"), gettext("Écart")],
        [
            [
                str(kinds[kind]),
                data[kind]["planned"],
                data[kind]["actual"],
                data[kind]["actual"] - data[kind]["planned"],
            ]
            for kind in (BudgetKind.EXPENSE, BudgetKind.INCOME)
        ]
        + [
            [
                gettext("Solde"),
                data["balance_planned"],
                data["balance_actual"],
                data["balance_actual"] - data["balance_planned"],
            ]
        ],
    )
    by_category = Table(
        "by_category",
        gettext("Par poste"),
        [
            gettext("Poste"),
            gettext("Nature"),
            gettext("Prévu"),
            gettext("Réalisé"),
            gettext("Écart"),
        ],
        [
            [
                str(categories[row["category"]]),
                str(kinds[row["kind"]]),
                row["planned"],
                row["actual"],
                row["actual"] - row["planned"],
            ]
            for row in data["by_category"]
        ],
    )
    return [totals, by_category]


def sponsors_section(edition: Edition) -> list[Table]:
    from django.db.models import Sum

    from apps.sponsors.models import Sponsor, SponsorStatus
    from apps.sponsors.services import totals

    data = totals(edition)
    statuses = dict(SponsorStatus.choices)
    by_status = Table(
        "by_status",
        gettext("Partenaires par statut (%(currency)s)") % {"currency": data["currency"]},
        [gettext("Statut"), gettext("Nombre")],
        [[str(statuses[status]), count] for status, count in data["by_status"].items()],
    )
    levels = (
        Sponsor.objects.filter(edition=edition)
        .exclude(status=SponsorStatus.DECLINED)
        .values("level__name_fr", "level__name_en")
        .annotate(n=Count("id"), agreed=Sum("agreed_amount"), received=Sum("received_amount"))
        .order_by("level__position", "level__name_fr")
    )
    by_level = Table(
        "by_level",
        gettext("Par niveau (hors refus)"),
        [gettext("Niveau"), gettext("Partenaires"), gettext("Convenu"), gettext("Reçu")],
        [
            [
                _label(item["level__name_fr"] or "—", item["level__name_en"]),
                item["n"],
                item["agreed"] or ZERO,
                item["received"] or ZERO,
            ]
            for item in levels
        ]
        + [[gettext("Total"), sum(item["n"] for item in levels), data["agreed"], data["received"]]],
    )
    return [by_status, by_level]


SECTIONS: tuple[Section, ...] = (
    Section("submissions", _("Soumissions"), C.SUBMISSIONS_READ, submissions_section, 10),
    Section("reviews", _("Relecture"), C.REVIEWS_MANAGE, reviews_section, 20),
    Section("registrations", _("Inscriptions"), C.REGISTRATIONS_READ, registrations_section, 30),
    Section("finance", _("Recettes"), C.FINANCE_READ, finance_section, 40),
    Section("attendance", _("Présence"), C.REGISTRATIONS_READ, attendance_section, 50),
    Section("satisfaction", _("Satisfaction"), C.SURVEYS_MANAGE, satisfaction_section, 60),
    Section("budget", _("Budget"), C.BUDGET_READ, budget_section, 70),
    Section("sponsors", _("Partenaires"), C.SPONSORS_READ, sponsors_section, 80),
)
BY_CODE = {section.code: section for section in SECTIONS}


def available(capabilities) -> list[Section]:
    held = set(capabilities)
    return [section for section in SECTIONS if section.capability in held]


def compute(section: Section, edition: Edition) -> list[Table]:
    return section.compute(edition)
