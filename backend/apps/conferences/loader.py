"""Chargement d'une édition réelle depuis un dossier versionné (décision T3, 19 octobre 2026).

Le dossier (``backend/data/editions/<nom>/``) contient ``edition.json`` et ses fichiers
(affiche, photos, logos). La commande ``load_edition`` le lit et crée, par les **services
métier** seulement (audit, validations et contrôles d'ordre des dates compris, comme un
opérateur dans la gestion) : la conférence si besoin, l'édition, ses thématiques, ses types de
communication, ses dates clés, ses paramètres et catégories d'inscription, ses partenaires et
leurs logos, ses fichiers publics (affiche comprise), les sections du portail posées sur les
pages du site, puis la publication et l'édition courante.

Pas de migration de données : une migration s'appliquerait à toutes les bases (celles des
tests comprises) et à toute autre installation. Une édition déjà présente (même code) est
refusée : on ne recharge pas par-dessus des données saisies ensuite dans la gestion.

Ce module orchestre plusieurs applications (portail, inscriptions, partenaires, comptes) :
leurs services sont importés dans la fonction, comme ``apps.qa.demo``, pour que
``conferences`` n'en dépende pas au chargement.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.conferences import services as conferences
from apps.conferences.models import Conference, Edition
from apps.core.actor import Actor

DATA_FILE = "edition.json"
ACTOR_LABEL = "cli:load_edition"
# Champs de l'édition acceptés dans le fichier (ceux de la fiche « Informations » et de la
# confidentialité) ; tout autre champ est refusé avant d'écrire quoi que ce soit.
EDITION_KEYS = frozenset(
    (*conferences.EDITION_INFO_FIELDS, "double_blind", "reviewers_per_submission")
)
DATE_KEYS = ("start_date", "end_date")


class EditionDataError(Exception):
    """Dossier ou fichier de données invalide, ou édition déjà chargée."""


@dataclass
class LoadReport:
    edition: str
    conference: str
    conference_created: bool
    counts: dict[str, int] = field(default_factory=dict)
    admin: str = ""


def read_edition_data(directory: Path) -> dict[str, Any]:
    """Lit et contrôle ``edition.json`` : champs connus, fichiers présents dans le dossier."""
    directory = Path(directory).resolve()
    path = directory / DATA_FILE
    if not path.is_file():
        raise EditionDataError(f"{path} introuvable.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EditionDataError(f"{path} : JSON invalide ({exc}).") from exc
    for key in ("conference", "edition", "tracks", "submission_types", "key_dates"):
        if key not in data:
            raise EditionDataError(f"Clé « {key} » absente de {DATA_FILE}.")
    unknown = set(data["edition"]) - EDITION_KEYS
    if unknown:
        raise EditionDataError(f"Champs d'édition inconnus : {', '.join(sorted(unknown))}.")
    for relative in _referenced_files(data):
        target = (directory / relative).resolve()
        if directory not in target.parents or not target.is_file():
            raise EditionDataError(f"Fichier absent ou hors du dossier : {relative}.")
    return data


def _referenced_files(data: dict[str, Any]) -> list[str]:
    files = [spec["path"] for spec in data.get("files", {}).values()]
    files += [sponsor["logo"] for sponsor in data.get("sponsors", []) if sponsor.get("logo")]
    return files


def _local_now(zone: str) -> dt.datetime:
    return timezone.localtime(timezone.now(), ZoneInfo(zone)).replace(tzinfo=None, microsecond=0)


def _at_local(value: str, zone: str) -> dt.datetime:
    """Heure locale de l'édition (naïve, convertie par le service, D13) ; « now » = maintenant."""
    if value == "now":
        return _local_now(zone)
    return dt.datetime.fromisoformat(value)


@transaction.atomic
def load_edition(
    directory: Path, *, admin_email: str = "", locale: str = "fr", publish: bool = True
) -> LoadReport:
    from apps.portal import services as portal
    from apps.portal.models import Page, Section
    from apps.registrations.services import pricing
    from apps.registrations.services.settings import update_registration_settings
    from apps.sponsors import services as sponsors

    directory = Path(directory).resolve()
    data = read_edition_data(directory)
    actor = Actor.command(ACTOR_LABEL)
    code = data["edition"]["code"]
    if Edition.objects.filter(code=code).exists():
        raise EditionDataError(f"L'édition {code} existe déjà : rien chargé.")

    conference = Conference.objects.filter(slug=data["conference"]["slug"]).first()
    conference_created = conference is None
    if conference is None:
        conference = conferences.create_conference(actor=actor, **data["conference"])
    fields = dict(data["edition"])
    for key in DATE_KEYS:
        if fields.get(key):
            fields[key] = dt.date.fromisoformat(fields[key])
    # Création par le service : le portail (pages, sections « données », menu) est semé par
    # le signal de création, comme pour toute édition.
    edition = conferences.create_edition(conference=conference, actor=actor, **fields)
    report = LoadReport(
        edition=edition.code, conference=conference.slug, conference_created=conference_created
    )
    zone = edition.timezone

    for position, track in enumerate(data["tracks"]):
        conferences.create_track(edition, {**track, "position": position}, actor=actor)
    for position, kind in enumerate(data["submission_types"]):
        conferences.create_submission_type(edition, {**kind, "position": position}, actor=actor)
    for key_date in data["key_dates"]:
        conferences.create_key_date(
            edition,
            {**key_date, "at_local": _at_local(key_date["at_local"], zone)},
            actor=actor,
        )
    report.counts.update(
        tracks=len(data["tracks"]),
        submission_types=len(data["submission_types"]),
        key_dates=len(data["key_dates"]),
    )

    registration = data.get("registration")
    if registration:
        update_registration_settings(edition, registration.get("settings", {}), actor=actor)
        periods = registration.get("periods", ["regular"])
        for position, spec in enumerate(registration.get("categories", [])):
            fees = spec.get("fees", {})
            category = pricing.create_category(
                edition,
                {key: value for key, value in spec.items() if key != "fees"}
                | {"position": position},
                actor=actor,
            )
            pricing.set_fees(
                category,
                [
                    {"period": period, "zone": zone_name, "amount": Decimal(amount)}
                    for period in periods
                    for zone_name, amount in fees.items()
                ],
                actor=actor,
            )
        report.counts["registration_categories"] = len(registration.get("categories", []))

    public_files: dict[str, Any] = {}
    for key, spec in data.get("files", {}).items():
        path = directory / spec["path"]
        kind = "document" if path.suffix.lower() == ".pdf" else "image"
        stored = portal.upload_file(
            edition,
            data=path.read_bytes(),
            name=path.name,
            kind=kind,
            title_fr=spec.get("title_fr", ""),
            title_en=spec.get("title_en", ""),
            actor=actor,
        )
        public_files[key] = portal.update_file(stored, {"published": True}, actor=actor)
    if "poster_image" in public_files:
        portal.set_poster(edition, public_files["poster_image"], actor=actor)
    report.counts["public_files"] = len(public_files)

    levels = {}
    for position, spec in enumerate(data.get("sponsor_levels", [])):
        levels[spec["key"]] = sponsors.create_level(
            edition,
            {key: value for key, value in spec.items() if key != "key"} | {"position": position},
            actor=actor,
        )
    for position, spec in enumerate(data.get("sponsors", [])):
        values = {key: value for key, value in spec.items() if key not in ("level", "logo")}
        sponsor = sponsors.create_sponsor(
            edition,
            values
            | {"level": levels[spec["level"]] if spec.get("level") else None}
            | {"published": True, "position": position},
            actor=actor,
        )
        if spec.get("logo"):
            logo = directory / spec["logo"]
            sponsors.set_logo(sponsor, data=logo.read_bytes(), name=logo.name, actor=actor)
    report.counts["sponsors"] = len(data.get("sponsors", []))

    pages = {page.slug: page for page in Page.objects.filter(edition=edition)}
    for spec in data.get("sections", []):
        if spec.get("seeded"):
            section = Section.objects.get(edition=edition, code=spec["code"])
        else:
            values = {key: value for key, value in spec.items() if key not in ("page", "image")}
            if spec.get("image"):
                values["image"] = public_files[spec["image"]]
            section = portal.create_section(edition, values, actor=actor)
        portal.attach_section(pages[spec["page"]], section, actor=actor)
    report.counts["sections"] = len(data.get("sections", []))

    if publish:
        conferences.set_edition_status(
            edition, "published", actor=actor, reason=f"Chargement de {directory.name}"
        )
        edition.refresh_from_db()
        conferences.set_current_edition(conference, edition, actor=actor)
    if admin_email:
        report.admin = _designate_admin(edition, admin_email, locale=locale, actor=actor)
    return report


def _designate_admin(edition: Edition, email: str, *, locale: str, actor: Actor) -> str:
    """Comme ``create_edition --admin-email`` : rôle ADMIN si l'adresse est vérifiée sur un
    compte, invitation sinon (D1 : aucun rôle global)."""
    from allauth.account.models import EmailAddress

    from apps.accounts.models import RoleSource
    from apps.accounts.roles import Role
    from apps.accounts.services.invitations import create_invitations
    from apps.accounts.services.roles import grant_role

    email = email.strip().lower()
    address = (
        EmailAddress.objects.filter(email__iexact=email, verified=True)
        .select_related("user")
        .first()
    )
    if address is not None:
        grant_role(
            user=address.user,
            edition=edition,
            role=Role.ADMIN,
            actor=actor,
            source=RoleSource.COMMAND,
        )
        return "Rôle ADMIN attribué au compte existant."
    create_invitations(
        edition=edition, emails=[email], role=Role.ADMIN, actor=actor, access=None, locale=locale
    )
    return "Invitation ADMIN envoyée (aucun compte vérifié pour cette adresse)."
