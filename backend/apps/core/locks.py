"""Verrou exclusif des commandes d'exploitation (plan L1 §8.2, ``LockedCommand``).

Deux mécanismes, dans cet ordre :

1. ``fcntl.flock`` non bloquant sur ``GESTCONF_LOCK_DIR/<commande>.lock`` (par défaut
   ``BASE_DIR/tmp``, dossier exclu du déploiement). Le noyau libère le verrou à la mort
   du processus : pas de verrou orphelin après un plantage.
2. Repli, si ``flock`` échoue pour une autre raison qu'un verrou déjà pris (système de
   fichiers qui ne le permet pas, dossier non inscriptible) : ``GET_LOCK`` de MariaDB,
   propre à la connexion (libéré à sa fermeture). Le nom inclut celui de la base : sur un
   serveur mutualisé, les noms de ``GET_LOCK`` sont communs à tous les comptes.

Si aucun des deux n'est disponible, la commande s'exécute sans verrou, avec un
avertissement : la réservation conditionnelle des tâches empêche déjà tout double
traitement, et les autres commandes sont idempotentes (risque R6).
"""

from __future__ import annotations

import enum
import errno
import fcntl
import hashlib
import logging
import os
from pathlib import Path

from django.db import DatabaseError, connection

logger = logging.getLogger(__name__)

# Longueur maximale d'un nom de GET_LOCK (MySQL 5.7+ ; MariaDB tolère davantage).
DB_LOCK_NAME_MAX_LENGTH = 64


class LockMechanism(enum.StrEnum):
    FLOCK = "flock"
    GET_LOCK = "get_lock"
    NONE = "none"


def db_lock_name(command: str) -> str:
    """Nom du verrou ``GET_LOCK`` : ``gestconf.<base>.<commande>``, condensé au-delà de 64."""
    name = f"gestconf.{connection.settings_dict['NAME']}.{command}"
    if len(name) <= DB_LOCK_NAME_MAX_LENGTH:
        return name
    return "gestconf." + hashlib.sha256(name.encode()).hexdigest()[:48]


class CommandLock:
    """Verrou d'une commande : ``acquire()`` renvoie ``False`` s'il est déjà pris ailleurs."""

    def __init__(self, name: str, lock_dir: Path) -> None:
        self.name = name
        self.path = Path(lock_dir) / f"{name}.lock"
        self.mechanism: LockMechanism | None = None
        self._fd: int | None = None
        self._db_lock: str | None = None

    def acquire(self) -> bool:
        try:
            return self._acquire_flock()
        except OSError as exc:
            logger.warning(
                "Verrou fichier indisponible pour %s (%s) : repli sur GET_LOCK.",
                self.name,
                errno.errorcode.get(exc.errno or 0, exc.__class__.__name__),
            )
        if connection.vendor == "mysql":
            acquired = self._acquire_get_lock()
            if acquired is not None:
                return acquired
        logger.warning(
            "Aucun verrou disponible pour %s : exécution sans verrou (la réservation "
            "conditionnelle des tâches reste exclusive, risque R6).",
            self.name,
        )
        self.mechanism = LockMechanism.NONE
        return True

    def _acquire_flock(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return False
        except OSError:
            os.close(fd)
            raise
        self._fd = fd
        self.mechanism = LockMechanism.FLOCK
        return True

    def _acquire_get_lock(self) -> bool | None:
        name = db_lock_name(self.name)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT GET_LOCK(%s, 0)", [name])
                (result,) = cursor.fetchone()
        except DatabaseError as exc:
            logger.warning("GET_LOCK indisponible pour %s (%s).", self.name, type(exc).__name__)
            return None
        if result == 1:
            self._db_lock = name
            self.mechanism = LockMechanism.GET_LOCK
            return True
        if result == 0:
            return False
        return None  # NULL : erreur côté serveur

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            finally:
                os.close(self._fd)
                self._fd = None
        if self._db_lock is not None:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", [self._db_lock])
            except DatabaseError:
                # Connexion perdue : le serveur a déjà libéré le verrou avec elle.
                logger.warning("RELEASE_LOCK impossible pour %s.", self.name)
            finally:
                self._db_lock = None
