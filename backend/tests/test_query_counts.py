"""Nombre de requêtes des listes chaudes (plan L9, S6 ; CLAUDE.md : pas de N+1).

Les données viennent de ``seed_volume`` à petite échelle : mêmes workflows qu'au volume de
l'étude (soumissions en évaluation, affectations, évaluations envoyées, brouillons,
inscriptions payées par virement). Deux contrôles :

- liste paginée : le même nombre de requêtes pour une page de 2 lignes et pour une page de
  100 (une requête par ligne ferait croître le second) ;
- toute liste : un plafond inférieur au nombre de lignes servies, qui exclut une requête par
  ligne même quand la réponse n'est pas paginée (classement, avancement, rapports).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import User
from apps.accounts.roles import OcFunction, Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import Edition
from apps.qa.volume import seed_volume

pytestmark = pytest.mark.django_db

# 24 soumissions (48 affectations, 16 par relecteur), 45 inscriptions dont 30 payées.
SIZES = {"submissions": 24, "reviewers": 3, "participants": 45, "drafts": 6}


@dataclass
class Volume:
    evaluation: int
    call: int
    chair: object
    finance: object
    reviewer: object
    desk: object


@pytest.fixture
def volume() -> Volume:
    report = seed_volume(**SIZES)
    reviewer = (
        User.objects.filter(
            roles__edition_id=report.editions["evaluation"], roles__role=Role.SC_MEMBER
        )
        .order_by("id")
        .first()
    )
    return Volume(
        evaluation=report.editions["evaluation"],
        call=report.editions["call"],
        chair=client_for(User.objects.get(email=report.committee["sc_chair"])),
        finance=client_for(User.objects.get(email=report.committee["oc_finance"])),
        reviewer=client_for(reviewer),
        desk=client_for(
            make_member(
                Edition.objects.get(pk=report.editions["call"]),
                Role.OC_MEMBER,
                oc_function=OcFunction.SECRETARIAT,
            )
        ),
    )


def measure(client, url: str, **params) -> tuple[int, dict | list]:
    with CaptureQueriesContext(connection) as context:
        response = client.get(url, params)
    assert response.status_code == 200, (url, response.content[:300])
    return len(context), response.json()


# Listes paginées : (client, édition, chemin sous /v1/manage/editions/<id>/, plafond,
# lignes au moins dans une page de 100).
PAGINATED = [
    ("chair", "evaluation", "submissions", 9, 24),
    ("chair", "evaluation", "review-submissions", 6, 24),
    ("finance", "call", "registrations", 6, 45),
    ("finance", "call", "billing/payments", 6, 30),
    ("finance", "call", "billing/documents", 6, 75),
]
# Vues non paginées : (client, édition, chemin, plafond). Chaque plafond est inférieur au
# nombre de lignes lues (24 soumissions, 48 affectations, 16 par relecteur, 45 inscriptions,
# 30 paiements et inscriptions confirmées).
UNPAGINATED = [
    ("reviewer", "evaluation", "reviews/assignments", 8),
    ("chair", "evaluation", "review-progress", 7),
    ("chair", "evaluation", "ranking", 6),
    ("chair", "evaluation", "submissions/stats", 5),
    ("chair", "evaluation", "reports/submissions", 9),
    ("chair", "evaluation", "reports/reviews", 5),
    ("finance", "call", "reports/registrations", 9),
    ("finance", "call", "reports/finance", 19),
    ("finance", "call", "reports/attendance", 7),
    ("finance", "call", "billing/dashboard", 19),
    ("desk", "call", "checkin/bundle", 9),
]


def test_s6_hot_lists_do_not_query_per_row(volume):
    """Un seul jeu de données (les factures PDF rendent le seed coûteux) ; tous les écarts
    sont rapportés ensemble. Le premier appel de chaque vue remplit les caches de session et
    de capacités ; seul le second est compté."""
    problems = []
    for who, edition, path, ceiling, rows in PAGINATED:
        client = getattr(volume, who)
        url = f"/v1/manage/editions/{getattr(volume, edition)}/{path}"
        measure(client, url, page_size=2)
        few, _page = measure(client, url, page_size=2)
        many, page = measure(client, url, page_size=100)
        if len(page["results"]) < rows:
            problems.append(f"{path} : {len(page['results'])} lignes, {rows} attendues")
        if many != few or many > ceiling:
            problems.append(f"{path} : {few} requêtes pour 2 lignes, {many} pour 100 (≤ {ceiling})")
    for who, edition, path, ceiling in UNPAGINATED:
        client = getattr(volume, who)
        url = f"/v1/manage/editions/{getattr(volume, edition)}/{path}"
        measure(client, url)
        count, _body = measure(client, url)
        if count > ceiling:
            problems.append(f"{path} : {count} requêtes (≤ {ceiling})")
    assert problems == []
