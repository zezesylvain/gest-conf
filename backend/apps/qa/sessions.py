"""Sessions pré-établies du test de charge (plan L9, S5).

Les limites de débit de la connexion (allauth, par adresse IP) arrêteraient un test de charge
lancé d'un seul poste au bout de quelques secondes : la commande ``loadtest_sessions`` ouvre
donc à l'avance une session par compte fictif, telle qu'une connexion réussie la laisse
(authentification, date de connexion, 2FA validée pour les comptes qui l'ont), et écrit les
cookies dans un fichier JSON lu par Locust. Le coût du hachage du mot de passe (R14) se
mesure à part, par quelques connexions réelles.

Comptes fictifs seulement (``@fictif.invalid``) ; fichier en 0600, jamais dans le dépôt ;
``--revoke`` supprime les sessions qu'il liste. La restauration de la sauvegarde d'avant le
test les efface de toute façon.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.http import HttpRequest
from django.middleware.csrf import get_token
from django.utils import timezone

from apps.accounts.middleware import LOGIN_AT_SESSION_KEY
from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.conferences.models import Edition
from apps.qa.fictitious import FICTITIOUS_CONFERENCE, FICTITIOUS_DOMAIN

AUTH_RECORDS = "account_authentication_methods"  # clé de session d'allauth
PERSONAS = ("committee", "reviewer", "author", "participant", "newcomer")


class SessionFileError(Exception):
    pass


@dataclass(frozen=True)
class Editions:
    evaluation: Edition
    call: Edition


def fictitious_editions() -> Editions:
    editions = {
        edition.code: edition
        for edition in Edition.objects.filter(conference__slug=FICTITIOUS_CONFERENCE)
    }
    try:
        return Editions(evaluation=editions["FICTIFEVAL"], call=editions["FICTIFAPPEL"])
    except KeyError as error:
        raise SessionFileError("Conférence fictive absente : lancer seed_volume.") from error


def _fictitious() -> Any:
    return User.objects.filter(email__iendswith="@" + FICTITIOUS_DOMAIN, is_active=True)


def personas(editions: Editions, counts: dict[str, int]) -> dict[str, list[User]]:
    """Comptes fictifs par profil de charge, dans un ordre stable."""
    from apps.registrations.models import Registration
    from apps.submissions.models import Submission, SubmissionStatus

    registered = Registration.objects.filter(edition=editions.call).values("user_id")
    drafts = Submission.objects.filter(edition=editions.call, status=SubmissionStatus.DRAFT).values(
        "submitter_id"
    )
    pools = {
        "committee": _fictitious()
        .filter(
            roles__edition__in=(editions.evaluation, editions.call),
            roles__role__in=(Role.SC_CHAIR, Role.OC_MEMBER),
        )
        .distinct(),
        "reviewer": _fictitious().filter(
            roles__edition=editions.evaluation, roles__role=Role.SC_MEMBER
        ),
        "author": _fictitious().filter(pk__in=drafts),
        "participant": _fictitious().filter(pk__in=registered),
        "newcomer": _fictitious()
        .filter(submissions__edition=editions.evaluation)
        .exclude(pk__in=registered)
        .distinct(),
    }
    return {
        name: list(pool.order_by("id")[: counts.get(name, 0)])
        for name, pool in pools.items()
        if counts.get(name, 0)
    }


def open_session(user: User, now: float) -> dict[str, str]:
    """Session d'un compte connecté : celle que laissent une connexion par mot de passe et,
    si le compte a une 2FA, sa validation (``MfaVerified``, D12)."""
    from allauth.mfa.models import Authenticator

    engine = import_module(settings.SESSION_ENGINE)
    store = engine.SessionStore()
    store[SESSION_KEY] = user._meta.pk.value_to_string(user)
    store[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
    store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store[LOGIN_AT_SESSION_KEY] = now
    records: list[dict[str, Any]] = [{"method": "password", "at": now, "email": user.email}]
    totp = Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).first()
    if totp is not None:
        records.insert(0, {"method": "mfa", "at": now, "id": totp.pk, "type": "totp"})
    store[AUTH_RECORDS] = records
    store.create()
    request = HttpRequest()
    token = get_token(request)
    return {
        "email": user.email,
        "session": store.session_key,
        "csrf_cookie": request.META["CSRF_COOKIE"],
        "csrf_token": token,
    }


def write_sessions(path: Path, counts: dict[str, int]) -> dict[str, int]:
    """Ouvre les sessions et écrit le fichier (0600, jamais écrasé)."""
    if path.exists():
        raise SessionFileError(f"{path} existe déjà : choisir un autre fichier.")
    editions = fictitious_editions()
    now = time.time()
    chosen = personas(editions, counts)
    data = {
        "created_at": timezone.now().isoformat(),
        "expires_in_hours": settings.SESSION_COOKIE_AGE // 3600,
        "cookies": {"session": settings.SESSION_COOKIE_NAME, "csrf": settings.CSRF_COOKIE_NAME},
        "editions": {"evaluation": editions.evaluation.pk, "call": editions.call.pk},
        "personas": {
            name: [open_session(user, now) for user in users] for name, users in chosen.items()
        },
    }
    # Comité : édition de ses listes (« evaluation » pour le comité scientifique, « call »
    # pour le CO « finances »), lue par les scénarios.
    scopes = {
        user.email: "evaluation"
        if user.roles.filter(edition=editions.evaluation).exists()
        else "call"
        for user in chosen.get("committee", [])
    }
    for item in data["personas"].get("committee", []):
        item["scope"] = scopes[item["email"]]
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)
    return {name: len(items) for name, items in data["personas"].items()}


def revoke_sessions(path: Path) -> int:
    """Supprime les sessions listées dans le fichier ; renvoie leur nombre."""
    engine = import_module(settings.SESSION_ENGINE)
    data = json.loads(path.read_text("utf-8"))
    keys = [item["session"] for items in data["personas"].values() for item in items]
    for key in keys:
        engine.SessionStore(session_key=key).delete()
    return len(keys)
