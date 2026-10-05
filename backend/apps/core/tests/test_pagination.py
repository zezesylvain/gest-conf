"""Pagination uniforme StandardPagination (plan L1 §9.1)."""

import pytest
from django.conf import settings

pytestmark = [pytest.mark.urls("apps.core.tests.urls"), pytest.mark.django_db]


def test_standard_pagination_is_the_default():
    assert (
        settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"]
        == "apps.core.pagination.StandardPagination"
    )


def test_default_page_size_is_25(client):
    payload = client.get("/paginated").json()
    assert payload["count"] == 230
    assert payload["results"] == list(range(25))
    assert payload["previous"] is None
    assert payload["next"].endswith("/paginated?page=2")


def test_page_size_parameter(client):
    payload = client.get("/paginated", {"page": 2, "page_size": 50}).json()
    assert payload["results"] == list(range(50, 100))


def test_page_size_is_capped_at_100(client):
    payload = client.get("/paginated", {"page_size": 500}).json()
    assert len(payload["results"]) == 100


def test_out_of_range_page_is_404(client):
    response = client.get("/paginated", {"page": 99})
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
