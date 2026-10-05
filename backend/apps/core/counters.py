"""Numérotation sans trou ni doublon (étude §8.3 ; références de soumission en L3,
factures en L6)."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from apps.core.models import Counter


def ensure_counter(scope: str) -> None:
    """Crée le compteur s'il n'existe pas, **hors contention** (à la création de son
    propriétaire : l'édition pour les références de soumission).

    Sous MariaDB (REPEATABLE READ), des ``SELECT … FOR UPDATE`` simultanés sur une ligne
    absente prennent des verrous d'intervalle, puis les insertions concurrentes
    s'interbloquent (erreur 1213, constatée par le test de concurrence) : la ligne doit
    exister avant le premier numéro demandé.
    """
    try:
        with transaction.atomic():
            Counter.objects.get_or_create(scope=scope)
    except IntegrityError:
        pass  # créé en parallèle : il existe


def next_value(scope: str) -> int:
    """Valeur suivante du compteur ``scope``, à appeler **dans** la transaction qui
    consomme le numéro : le verrou de ligne (``SELECT … FOR UPDATE``) sérialise les
    appels concurrents, et un échec de la transaction annule l'incrément (pas de trou).

    Le compteur doit exister (``ensure_counter``) ; le repli qui le crée ici n'est sûr que
    sans concurrence (voir ``ensure_counter``).
    """
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_value() doit être appelé dans une transaction.")
    counter = Counter.objects.select_for_update().filter(scope=scope).first()
    if counter is None:
        # Création concurrente : la contrainte d'unicité départage, le perdant relit.
        try:
            with transaction.atomic():
                Counter.objects.create(scope=scope, value=0)
        except IntegrityError:
            pass
        counter = Counter.objects.select_for_update().get(scope=scope)
    counter.value += 1
    counter.save(update_fields=["value"])
    return counter.value
