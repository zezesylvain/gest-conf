"""Fixtures communes à toutes les suites de tests (pytest-django)."""

import os
from collections.abc import Mapping

import pytest
from django.conf import settings
from django.core.management import call_command
from rest_framework.test import APIClient

# Moteur de la base de test : SQLite par défaut, MariaDB si DATABASE_URL le demande.
ON_MARIADB = settings.DATABASES["default"]["ENGINE"] == "django.db.backends.mysql"


def check_required_engine(environ: Mapping[str, str], on_mariadb: bool) -> None:
    """Refuse de lancer la suite hors MariaDB quand ``GESTCONF_REQUIRE_MARIADB=1``.

    La CI pose cette variable sur son étape MariaDB : si DATABASE_URL disparaît du
    job ou n'est plus lue par config.settings.test, la suite tournerait sur SQLite,
    ignorerait les tests ``mariadb_only`` et resterait verte sans rien prouver.
    """
    if environ.get("GESTCONF_REQUIRE_MARIADB") == "1" and not on_mariadb:
        raise pytest.UsageError(
            "GESTCONF_REQUIRE_MARIADB=1 mais la base de test n'est pas MariaDB "
            "(DATABASE_URL absente ou ignorée)."
        )


def pytest_configure(config: pytest.Config) -> None:
    check_required_engine(os.environ, ON_MARIADB)


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("mariadb_only") and not ON_MARIADB:
        pytest.skip("sans objet hors MariaDB (lancer avec DATABASE_URL=mysql://...)")


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    """Après la création de la base de test, crée la table du cache partagé.

    Les tests exercent ainsi le vrai DatabaseCache (limites de débit, sonde
    /health), comme en production, où « createcachetable » suit « migrate ».
    """
    with django_db_blocker.unblock():
        call_command("createcachetable", verbosity=0)


@pytest.fixture(autouse=True)
def _fresh_health_cache_probe():
    """Chaque test repart sans résultat mémorisé de la sonde du cache de /health."""
    from apps.core.views import reset_cache_probe

    reset_cache_probe()
    yield
    reset_cache_probe()


@pytest.fixture(autouse=True)
def _isolated_command_locks(settings, tmp_path):
    """Verrous des commandes cron dans un dossier propre au test, jamais dans backend/tmp."""
    settings.GESTCONF_LOCK_DIR = tmp_path / "locks"
    # Fichiers déposés (lot L2) : jamais dans le dépôt pendant les tests.
    settings.GESTCONF_FILES_DIR = tmp_path / "files"


@pytest.fixture
def api_client() -> APIClient:
    """Client DRF anonyme (contrôle CSRF désactivé, comme le client de Django)."""
    return APIClient()


@pytest.fixture
def csrf_api_client() -> APIClient:
    """Client DRF qui impose le contrôle CSRF, comme un navigateur."""
    return APIClient(enforce_csrf_checks=True)


@pytest.fixture
def user(db):
    from apps.accounts.tests.factories import UserFactory

    return UserFactory()


@pytest.fixture
def auth_client(user) -> APIClient:
    """Client DRF connecté par une vraie session Django (``force_login``)."""
    client = APIClient()
    client.force_login(user)
    return client
