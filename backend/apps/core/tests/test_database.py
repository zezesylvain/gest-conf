"""Configuration de la base MariaDB (plan L1 §3.1, étape L1.1)."""

import pytest
from django.core.checks import run_checks
from django.db import connection

from config.settings.base import MARIADB_SQL_MODE, database_from_env


def test_database_from_env_forces_strict_sql_mode(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@localhost:3306/base")
    options = database_from_env()["OPTIONS"]
    assert options["charset"] == "utf8mb4"
    assert options["init_command"] == f"SET SESSION sql_mode='{MARIADB_SQL_MODE}'"
    assert "STRICT_TRANS_TABLES" in MARIADB_SQL_MODE.split(",")


def test_database_from_env_leaves_sqlite_alone(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://:memory:")
    assert "init_command" not in database_from_env().get("OPTIONS", {})


def sql_modes(cursor) -> tuple[set[str], set[str]]:
    """Modes SQL (global, session) de la connexion du curseur."""
    cursor.execute("SELECT @@GLOBAL.sql_mode, @@SESSION.sql_mode")
    global_mode, session_mode = cursor.fetchone()
    return set(filter(None, global_mode.split(","))), set(filter(None, session_mode.split(",")))


def skip_unless_global_mode_differs(global_mode: set[str]) -> None:
    """Prémisse de la preuve : le mode global du serveur diffère de celui de l'application.

    Une connexion hérite du mode global ; si les deux sont égaux, un mode de session
    égal à MARIADB_SQL_MODE ne prouve plus que init_command a été appliqué (cas d'une
    image de CI alignée sur un serveur o2switch déjà configuré ainsi, décision H-1).
    """
    if global_mode == set(MARIADB_SQL_MODE.split(",")):
        pytest.skip(
            "mode global du serveur identique à MARIADB_SQL_MODE : l'application de "
            "init_command ne peut pas être distinguée (test sans objet sur ce serveur)"
        )


@pytest.mark.mariadb_only
@pytest.mark.django_db
def test_connection_sql_mode_is_strict():
    """La connexion de Django travaille exactement dans le mode de l'application (R19)."""
    with connection.cursor() as cursor:
        _, session_mode = sql_modes(cursor)
    assert "STRICT_TRANS_TABLES" in session_mode
    assert session_mode == set(MARIADB_SQL_MODE.split(","))


@pytest.mark.mariadb_only
@pytest.mark.django_db
def test_connection_sql_mode_comes_from_init_command():
    """Le mode strict vient de la connexion (init_command), pas du réglage global du serveur.

    Prouvé seulement si le mode global diffère (MariaDB 10.11 par défaut y ajoute
    NO_AUTO_CREATE_USER) ; sinon le test est ignoré, avec son motif, plutôt que de
    réussir sans rien prouver.
    """
    with connection.cursor() as cursor:
        global_mode, session_mode = sql_modes(cursor)
    skip_unless_global_mode_differs(global_mode)
    assert session_mode != global_mode
    assert session_mode == set(MARIADB_SQL_MODE.split(","))


@pytest.mark.mariadb_only
@pytest.mark.django_db
def test_new_connection_applies_init_command():
    raw = connection.get_new_connection(connection.get_connection_params())
    try:
        with raw.cursor() as cursor:
            global_mode, session_mode = sql_modes(cursor)
        skip_unless_global_mode_differs(global_mode)
        assert session_mode != global_mode
        assert session_mode == set(MARIADB_SQL_MODE.split(","))
    finally:
        raw.close()


@pytest.mark.mariadb_only
@pytest.mark.django_db
def test_no_strict_mode_warning():
    """Contrôle mysql.W002 de Django : mode strict actif sur la connexion."""
    ids = {message.id for message in run_checks(databases=["default"])}
    assert "mysql.W002" not in ids


@pytest.mark.parametrize(
    ("environ", "on_mariadb", "refused"),
    [
        ({"GESTCONF_REQUIRE_MARIADB": "1"}, False, True),
        ({"GESTCONF_REQUIRE_MARIADB": "1"}, True, False),
        ({}, False, False),
        ({"GESTCONF_REQUIRE_MARIADB": "0"}, False, False),
    ],
)
def test_ci_refuses_to_run_off_mariadb_when_required(environ, on_mariadb, refused):
    """Garde-fou de la CI : l'étape MariaDB ne peut pas passer en silence sur SQLite."""
    from conftest import check_required_engine

    if refused:
        with pytest.raises(pytest.UsageError, match="GESTCONF_REQUIRE_MARIADB"):
            check_required_engine(environ, on_mariadb)
    else:
        check_required_engine(environ, on_mariadb)
