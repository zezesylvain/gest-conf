"""RG-04 : garde-fous du double aveugle, posés avant le premier endpoint relecteur (plan L4,
H9). Le test de fuite de chaque route relecteur est dans ``test_leaks.py`` (L4.3)."""

from __future__ import annotations

import importlib
import pkgutil
from typing import ClassVar

import pytest
from django.urls import URLPattern, URLResolver, get_resolver
from rest_framework import serializers

import apps
from apps.reviews.anonymity import (
    IDENTITY_FIELDS,
    ReviewerSerializerMixin,
    find_identity_leaks,
    identity_violations,
    reviewer_serializers,
)
from apps.submissions.models import Submission, SubmissionAuthor, SubmissionFile

# Routes relecteur couvertes par un test de fuite (nom d'URL → test de ``test_leaks.py``). Une
# route nommée « reviewer-… » absente d'ici fait échouer test_every_reviewer_route_is_leak_tested.
LEAK_TESTED_ROUTES: dict[str, str] = {
    "reviewer-assignments-list": "test_rg04_leak_assignments_list",
    "reviewer-assignments-detail": "test_rg04_leak_assignment_detail",
    "reviewer-assignments-file": "test_rg04_leak_file_has_a_generic_name",
    "reviewer-assignments-authors": "test_rg04_leak_authors_route_is_closed_in_double_blind",
    "reviewer-assignments-decline": "test_rg04_leak_decline",
    "reviewer-review": "test_rg04_leak_review_save",
    "reviewer-review-submit": "test_rg04_leak_review_submit",
    "reviewer-discussion": "test_rg04_leak_discussion",
    "reviewer-expertise": "test_rg04_leak_expertise",
}


def _import_all_serializer_modules() -> None:
    """Charge tous les modules de sérialiseurs : le registre relecteur est alors complet."""
    for module in pkgutil.iter_modules(apps.__path__):
        for name in ("serializers", "reviewer_serializers"):
            try:
                importlib.import_module(f"apps.{module.name}.{name}")
            except ModuleNotFoundError as error:
                if error.name != f"apps.{module.name}.{name}":
                    raise


def test_rg04_every_reviewer_serializer_is_a_clean_whitelist():
    """RG-04 : aucun sérialiseur relecteur n'expose un champ du registre d'identité."""
    _import_all_serializer_modules()
    problems = [p for cls in reviewer_serializers() for p in identity_violations(cls)]
    assert problems == []


def test_rg04_registry_names_real_fields():
    """Le registre ne doit pas viser un champ disparu (renommage silencieux)."""
    from django.apps import apps as registry

    for label, names in IDENTITY_FIELDS.items():
        model = registry.get_model(label)
        if names == "*":
            continue
        known = {field.name for field in model._meta.get_fields()}
        assert set(names) <= known, (label, set(names) - known)


# Sérialiseurs fautifs (non enregistrés : ils ne dérivent pas des bases relecteur).


class _Author(ReviewerSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = SubmissionAuthor
        fields = ("position",)


class _Leaky(ReviewerSerializerMixin, serializers.ModelSerializer):
    submitter_email = serializers.CharField(source="submitter.email")
    file_name = serializers.SerializerMethodField()
    authors = _Author(many=True)

    class Meta:
        model = Submission
        fields = ("title", "submitter_email", "file_name", "authors")

    def get_file_name(self, submission):  # pragma: no cover - jamais appelé
        return ""


class _Excluding(ReviewerSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = SubmissionFile
        exclude = ("original_name",)


def test_rg04_violations_detected():
    problems = " | ".join(identity_violations(_Leaky))
    assert "Submission.submitter est une donnée d'identité" in problems  # par source
    assert "file_name : champ calculé sans justification" in problems
    assert "authors : sérialiseur imbriqué hors liste blanche" in problems
    assert "Submission.authors est une donnée d'identité" in problems
    assert identity_violations(_Excluding) == ["_Excluding : « exclude » interdit (liste blanche)"]


def test_rg04_justified_computed_field_and_safe_fields_pass():
    class Clean(ReviewerSerializerMixin, serializers.ModelSerializer):
        reviewer_computed: ClassVar[dict[str, str]] = {
            "pages": "Nombre de pages du PDF nettoyé : pas une identité."
        }
        pages = serializers.SerializerMethodField()

        class Meta:
            model = Submission
            fields = ("reference", "title", "abstract", "keywords", "pages")

        def get_pages(self, submission):  # pragma: no cover - jamais appelé
            return 0

    assert identity_violations(Clean) == []


def test_rg04_leak_finder_spots_tracers_and_identity_keys():
    payload = {
        "title": "Étude",
        "items": [{"note": "Merci à TRACEUR-Koné pour son aide"}, {"email": "x@y.z"}],
        "file": {"name": "GC27-0001.pdf"},
    }
    leaks = find_identity_leaks(payload, ["traceur-koné", "", "absent"])
    assert leaks == [
        "$.items[0].note : traceur « traceur-koné »",
        "$.items[1].email : clé d'identité « email »",
    ]
    assert find_identity_leaks({"title": "Étude"}, ["traceur"]) == []


def _reviewer_route_names() -> set[str]:
    def walk(patterns):
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                yield from walk(pattern.url_patterns)
            elif isinstance(pattern, URLPattern) and (pattern.name or "").startswith("reviewer-"):
                yield pattern.name

    return set(walk(get_resolver().url_patterns))


@pytest.mark.django_db
def test_every_reviewer_route_is_leak_tested():
    """Une route relecteur (nom « reviewer-… ») ne peut pas échapper au test de fuite."""
    from apps.reviews.tests import test_leaks

    assert _reviewer_route_names() == set(LEAK_TESTED_ROUTES)
    assert all(callable(getattr(test_leaks, name, None)) for name in LEAK_TESTED_ROUTES.values())
