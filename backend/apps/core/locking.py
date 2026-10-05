"""Verrous des commandes cron (règle n° 9, plan L1 §8.2, décision d'hébergement H-5).

Deux mécanismes, au choix par ``GESTCONF_COMMAND_LOCK`` :

- ``flock`` (défaut) : ``fcntl.flock`` non bloquant sur
  ``GESTCONF_LOCK_DIR/<nom>.lock`` (dossier ``tmp/`` de l'application, exclu du
  rsync). Libéré par le noyau à la mort du processus. Comportement sur le système
  de fichiers d'o2switch à vérifier (contrôle V15) ;
- ``database`` : ``GET_LOCK('gestconf.<nom>', 0)`` de MariaDB, tenu par la
  connexion de la commande. Repli si ``flock`` n'est pas fiable (V12).

Dans les deux cas, la réservation conditionnelle des jobs (``apps.core.jobs``)
garantit qu'aucun job n'est traité deux fois, même sans verrou.
"""

from __future__ import annotations

import fcntl
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

LOCK_NAME_PATTERN = re.compile(r"^[a-z0-9_]{1,48}$")
LOCK_BACKENDS = ("flock", "database")


@contextmanager
def _flock(name: str) -> Iterator[bool]:
    directory = Path(settings.GESTCONF_LOCK_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / f"{name}.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def _database_lock(name: str) -> Iterator[bool]:
    if connection.vendor != "mysql":
        raise ImproperlyConfigured("GESTCONF_COMMAND_LOCK=database exige MariaDB (GET_LOCK).")
    key = f"gestconf.{name}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK(%s, 0)", [key])
        acquired = cursor.fetchone()[0] == 1
    if not acquired:
        yield False
        return
    try:
        yield True
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", [key])


@contextmanager
def command_lock(name: str) -> Iterator[bool]:
    """Verrou exclusif non bloquant ; produit ``True`` s'il est obtenu, ``False`` sinon."""
    if not LOCK_NAME_PATTERN.match(name):
        raise ValueError(f"Nom de verrou invalide : {name!r}")
    backend = settings.GESTCONF_COMMAND_LOCK
    if backend == "flock":
        with _flock(name) as acquired:
            yield acquired
    elif backend == "database":
        with _database_lock(name) as acquired:
            yield acquired
    else:
        raise ImproperlyConfigured(f"GESTCONF_COMMAND_LOCK inconnu : {backend!r} {LOCK_BACKENDS}")
