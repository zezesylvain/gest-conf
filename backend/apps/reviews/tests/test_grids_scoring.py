"""Lot L4, étape L4.1 : calcul des notes (H4), grilles (RG-05, H3), contrôles d'intégrité."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.roles import Role
from apps.accounts.tests.roles_helpers import client_for, make_member
from apps.conferences.models import EditionStatus
from apps.conferences.tests.factories import EditionFactory, SubmissionTypeFactory
from apps.core.actor import Actor, ActorKind
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog
from apps.reviews import integrity
from apps.reviews.models import (
    Criterion,
    EvaluationGrid,
    Review,
    ReviewAssignment,
    ReviewScore,
)
from apps.reviews.services import grids
from apps.reviews.services.scoring import CriterionWeight, divergence, final_score, weighted_score
from apps.submissions.tests.factories import complete_submission

COMMAND = Actor.command("cli:test")
db = pytest.mark.django_db
D = Decimal


def study_criteria(required=(True,) * 5):
    weights = (25, 30, 15, 15, 15)
    return [
        CriterionWeight(key=i, weight=D(w), required=r)
        for i, (w, r) in enumerate(zip(weights, required, strict=True))
    ]


# --- Calcul (H4) -------------------------------------------------------------------------------


def test_h4_study_example_gives_74():
    """Étude §5.1 : notes (4 ; 3 ; 5 ; 4 ; 3), poids (25 ; 30 ; 15 ; 15 ; 15), échelle 0-5 :
    3,70 / 5 → 74 / 100."""
    values = {0: D(4), 1: D(3), 2: D(5), 3: D(4), 4: D(3)}
    assert weighted_score(study_criteria(), values, 0, 5) == D("74.00")


def test_h4_scale_min_is_subtracted():
    """Échelle 1-10 : la note minimale vaut 0, la maximale 100."""
    criteria = [CriterionWeight(key="a", weight=D(100))]
    assert weighted_score(criteria, {"a": D(1)}, 1, 10) == D("0.00")
    assert weighted_score(criteria, {"a": D(10)}, 1, 10) == D("100.00")
    assert weighted_score(criteria, {"a": D("5.5")}, 1, 10) == D("50.00")


def test_h4_rounding_half_up_to_two_decimals():
    criteria = [CriterionWeight(key="a", weight=D(100))]
    # 1/3 de l'échelle 0-3 → 33,333… ; 0,5/3 → 16,666… ; 0,0375/3 → 1,25 exactement.
    assert weighted_score(criteria, {"a": D(1)}, 0, 3) == D("33.33")
    assert weighted_score(criteria, {"a": D("0.5")}, 0, 3) == D("16.67")
    assert weighted_score(criteria, {"a": D("0.1")}, 0, 8) == D("1.25")


def test_h4_optional_criterion_excluded_and_required_missing_gives_none():
    criteria = study_criteria(required=(True, True, True, True, False))
    values = {0: D(4), 1: D(3), 2: D(5), 3: D(4)}  # critère facultatif 4 non noté
    # (4*25 + 3*30 + 5*15 + 4*15) / 85 = 3,8235… → 76,47 / 100
    assert weighted_score(criteria, values, 0, 5) == D("76.47")
    assert weighted_score(study_criteria(), values, 0, 5) is None
    assert weighted_score(criteria, {}, 0, 5) is None


def test_h4_final_score_mean_or_confidence_weighted():
    rows = [(D("80"), 5), (D("40"), 1)]
    assert final_score(rows) == D("60.00")
    assert final_score(rows, confidence_weighted=True) == D("73.33")
    assert final_score([(D("70"), None)], confidence_weighted=True) == D("70.00")
    assert final_score([]) is None


def test_h12_divergence_is_max_minus_min():
    assert divergence([D("80"), D("40"), D("65")]) == D("40.00")
    assert divergence([D("80")]) == D("0.00")


# --- Grilles (RG-05, H3) -----------------------------------------------------------------------


@db
def test_rg05_default_grid_from_the_study_weighs_100():
    edition = EditionFactory()
    grid = grids.create_grid(edition, name="Grille", actor=COMMAND)
    assert (grid.version, grid.scale_min, grid.scale_max, grid.locked_at) == (1, 0, 5, None)
    weights = list(grid.criteria.order_by("position").values_list("weight", flat=True))
    assert weights == [D(25), D(30), D(15), D(15), D(15)]
    assert AuditLog.objects.get(action="grid.created").after["criteria"][0]["code"] == "originalite"


@pytest.mark.parametrize(
    ("criteria", "message"),
    [
        ([{"code": "a", "label_fr": "A", "weight": "60"}], "somme des poids doit valoir 100"),
        (
            [
                {"code": "a", "label_fr": "A", "weight": "50"},
                {"code": "a", "label_fr": "B", "weight": "50"},
            ],
            "uniques",
        ),
        ([{"code": "a", "label_fr": "A", "weight": "100.005"}], "deux décimales"),
        ([{"code": "a", "label_fr": "", "weight": "100"}], "Libellé français"),
        ([], "De 1 à 20"),
    ],
)
@db
def test_rg05_criteria_refused(criteria, message):
    """RG-05 : somme exactement 100, codes uniques, poids à deux décimales, libellé FR."""
    with pytest.raises(Invalid) as error:
        grids.create_grid(EditionFactory(), name="G", criteria=criteria, actor=COMMAND)
    assert message in " ".join(str(item) for item in error.value.fields["criteria"])


@db
def test_rg05_decimal_weights_summing_to_100_accepted():
    criteria = [
        {"code": "a", "label_fr": "A", "weight": "33.33"},
        {"code": "b", "label_fr": "B", "weight": "33.33"},
        {"code": "c", "label_fr": "C", "weight": "33.34", "is_required": False},
    ]
    grid = grids.create_grid(EditionFactory(), name="G", criteria=criteria, actor=COMMAND)
    assert grid.criteria.get(code="c").is_required is False


@db
def test_rg05_locked_grid_is_duplicated_not_modified():
    """RG-05 : une grille utilisée est verrouillée ; on la duplique en nouvelle version."""
    edition = EditionFactory()
    grid = grids.create_grid(edition, name="Grille", actor=COMMAND)
    grids.lock_grid(grid)
    assert grid.locked_at is not None
    for attempt in (
        lambda: grids.update_grid(grid, {"name": "Autre"}, actor=COMMAND),
        lambda: grids.delete_grid(grid, actor=COMMAND),
    ):
        with pytest.raises(RuleViolation) as error:
            attempt()
        assert error.value.code == "grid_locked"
    copy = grids.duplicate_grid(grid, actor=COMMAND)
    assert (copy.version, copy.locked_at) == (2, None)
    assert copy.criteria.count() == 5
    grids.update_grid(
        copy,
        {"name": "Grille v2"},
        criteria=[{"code": "unique", "label_fr": "Note globale", "weight": "100"}],
        actor=COMMAND,
    )
    assert list(copy.criteria.values_list("code", flat=True)) == ["unique"]
    assert grid.criteria.count() == 5  # la version utilisée reste intacte


@db
def test_h3_grid_for_type_falls_back_to_all_types():
    edition = EditionFactory()
    oral = SubmissionTypeFactory(edition=edition)
    poster = SubmissionTypeFactory(edition=edition)
    general = grids.create_grid(edition, name="Toutes", actor=COMMAND)
    oral_v1 = grids.create_grid(edition, name="Oral", submission_type=oral, actor=COMMAND)
    oral_v2 = grids.duplicate_grid(oral_v1, actor=COMMAND)
    assert grids.grid_for(edition, oral) == oral_v2
    assert grids.grid_for(edition, poster) == general
    assert grids.grid_for(edition, None) == general
    assert grids.grid_for(EditionFactory(), None) is None


@db
def test_grid_writes_refused_on_archived_edition():
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    member = make_member(edition, Role.CHAIR)
    with pytest.raises(RuleViolation) as error:
        grids.create_grid(edition, name="G", actor=Actor(kind=ActorKind.USER, user=member))
    assert error.value.code == "edition_archived"


# --- API ----------------------------------------------------------------------------------------


@db
def test_grid_api_create_with_criteria_type_and_duplicate():
    edition = EditionFactory()
    poster = SubmissionTypeFactory(edition=edition, code="poster")
    client = client_for(make_member(edition, Role.SC_CHAIR))
    base = f"/v1/manage/editions/{edition.pk}/grids"
    response = client.post(
        base,
        {
            "name": "Poster",
            "submission_type": "poster",
            "scale_min": 1,
            "scale_max": 10,
            "criteria": [
                {"code": "fond", "label_fr": "Fond", "weight": "60"},
                {"code": "forme", "label_fr": "Forme", "weight": "40", "is_required": False},
            ],
        },
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["submission_type"] == "poster" and body["scale_max"] == 10
    assert [c["weight"] for c in body["criteria"]] == ["60.00", "40.00"]
    bad = client.patch(
        f"{base}/{body['id']}",
        {"criteria": [{"code": "x", "label_fr": "X", "weight": "99"}]},
        format="json",
    )
    assert bad.status_code == 400 and "criteria" in bad.json()["fields"]
    assert (
        client.post(base, {"name": "X", "submission_type": "inconnu"}, format="json").status_code
        == 400
    )
    copy = client.post(f"{base}/{body['id']}/duplicate").json()
    assert copy["version"] == 2 and copy["is_locked"] is False
    assert EvaluationGrid.objects.filter(edition=edition, submission_type=poster).count() == 2


# --- Intégrité ------------------------------------------------------------------------------------


@db
def test_integrity_checks_detect_bad_weights_and_tampered_scores():
    edition = EditionFactory()
    grid = grids.create_grid(edition, name="Grille", actor=COMMAND)
    assert integrity.check_grid_weights() == []
    Criterion.objects.filter(grid=grid, code="impact").update(weight=D("10"))
    assert integrity.check_grid_weights() == [f"grille {grid.pk} : somme des poids 95.00"]
    Criterion.objects.filter(grid=grid, code="impact").update(weight=D("15"))

    submission = complete_submission(edition)
    assignment = ReviewAssignment.objects.create(
        submission=submission, reviewer=submission.submitter, assigned_at=timezone.now()
    )
    review = Review.objects.create(assignment=assignment, grid=grid, weighted_score=D("74.00"))
    for code, value in zip(
        ("originalite", "methode", "pertinence", "redaction", "impact"),
        (4, 3, 5, 4, 3),
        strict=True,
    ):
        ReviewScore.objects.create(
            review=review, criterion=grid.criteria.get(code=code), value=value
        )
    assert integrity.review_score(review) == D("74.00")
    assert integrity.check_review_scores() == []
    Review.objects.filter(pk=review.pk).update(weighted_score=D("99.00"))
    assert integrity.check_review_scores() == [
        f"évaluation {review.pk} : note stockée différente du calcul"
    ]
