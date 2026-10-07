"""Partenaires (plan L8, N5 ; étude M13). Seul module qui écrit niveaux, fiches et
contreparties.

- Montants en ``Decimal`` exacts dans la devise de l'édition ; contribution « reçue » :
  montant et date obligatoires. Le total reçu alimente la ligne « partenariats » du budget
  (``apps.logistics``, source calculée).
- Le **contact** d'un partenaire n'est jamais publié ni écrit en clair au journal (le
  journal refuse les adresses) : seul le fait qu'il a changé y figure.
- Ce qui change la page publique « Partenaires » (niveaux, partie publique d'un partenaire
  publié, publication, logo) porte ``public: true`` au journal : le portail le compte comme
  une modification non publiée (L2), visible après ``deploy.sh --portal-only``.
- Logo : image publique de nature ``logo`` (réencodée sans métadonnées, 600 px au plus),
  publiée avec le partenaire, absente de l'écran des fichiers du portail.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import transaction
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition
from apps.core import public_files
from apps.core.actor import Actor
from apps.core.audit import mask_emails, record
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.models import PublicFileKind
from apps.core.money import is_exact
from apps.sponsors.models import LogoSize, Sponsor, SponsorBenefit, SponsorLevel, SponsorStatus

ZERO = Decimal(0)
LEVEL_FIELDS = frozenset(SponsorLevel.AUDIT_FIELDS)
SPONSOR_FIELDS = frozenset(
    (*Sponsor.PUBLIC_FIELDS, *Sponsor.PRIVATE_FIELDS, *Sponsor.CONTACT_FIELDS)
)
TEXT_LIMITS = {
    "name_fr": 100,
    "name_en": 100,
    "benefits_fr": 2000,
    "benefits_en": 2000,
    "name": 150,
    "description_fr": 1000,
    "description_en": 1000,
    "contact_name": 150,
    "contact_phone": 40,
    "note": 2000,
}


def _currency(edition: Edition) -> str:
    from apps.registrations.services.settings import registration_settings

    return registration_settings(edition).currency


def _amount(edition: Edition, name: str, value: Any, errors: dict) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError):
        errors[name] = [_("Montant attendu.")]
        return None
    if not amount.is_finite() or amount < 0:
        errors[name] = [_("Montant positif ou nul attendu.")]
    elif amount >= Decimal("1e10"):
        errors[name] = [_("Montant trop élevé.")]
    elif not is_exact(amount, _currency(edition)):
        errors[name] = [
            _("Trop de décimales pour la devise %(currency)s.") % {"currency": _currency(edition)}
        ]
    return amount


def _texts(data: Mapping[str, Any], errors: dict) -> dict[str, Any]:
    clean = {}
    for name, limit in TEXT_LIMITS.items():
        if name in data:
            value = (data[name] or "").strip()
            if len(value) > limit:
                errors[name] = [_("%(limit)s caractères au plus.") % {"limit": limit}]
            clean[name] = value
    return clean


def _position(data: Mapping[str, Any], errors: dict) -> dict[str, Any]:
    if "position" not in data:
        return {}
    position = data["position"]
    if not isinstance(position, int) or isinstance(position, bool) or position < 0:
        errors["position"] = [_("Position positive ou nulle attendue.")]
    return {"position": position}


def _check_unknown(data: Mapping[str, Any], allowed: frozenset[str]) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})


def _value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


# --- Niveaux ------------------------------------------------------------------------------------


def _clean_level(edition: Edition, data: Mapping[str, Any], *, creating: bool) -> dict[str, Any]:
    _check_unknown(data, LEVEL_FIELDS)
    errors: dict[str, list] = {}
    clean = _texts(data, errors)
    clean.update(_position(data, errors))
    if creating and not clean.get("name_fr"):
        errors["name_fr"] = [_("Nom obligatoire.")]
    if "name_fr" in clean and not clean["name_fr"]:
        errors["name_fr"] = [_("Nom obligatoire.")]
    if "amount" in data:
        clean["amount"] = _amount(edition, "amount", data["amount"], errors)
    if "logo_size" in data:
        if data["logo_size"] not in LogoSize.values:
            errors["logo_size"] = [_("Taille inconnue.")]
        clean["logo_size"] = data["logo_size"]
    if errors:
        raise Invalid(fields=errors)
    return clean


def _level_snapshot(level: SponsorLevel) -> dict[str, Any]:
    return mask_emails({name: _value(getattr(level, name)) for name in SponsorLevel.AUDIT_FIELDS})


@transaction.atomic
def create_level(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> SponsorLevel:
    ensure_editable(edition)
    level = SponsorLevel.objects.create(
        edition=edition, **_clean_level(edition, data, creating=True)
    )
    record(
        "sponsor_level.created",
        actor=actor,
        edition=edition,
        obj=level,
        after=_level_snapshot(level),
    )
    return level


@transaction.atomic
def update_level(level: SponsorLevel, data: Mapping[str, Any], *, actor: Actor) -> SponsorLevel:
    ensure_editable(level.edition)
    level = SponsorLevel.objects.select_for_update().select_related("edition").get(pk=level.pk)
    clean = _clean_level(level.edition, data, creating=False)
    before = _level_snapshot(level)
    for name, value in clean.items():
        setattr(level, name, value)
    level.save()
    after = _level_snapshot(level)
    changed = [name for name in after if after[name] != before[name]]
    if changed:
        record(
            "sponsor_level.updated",
            actor=actor,
            edition=level.edition,
            obj=level,
            before={name: before[name] for name in changed},
            after={name: after[name] for name in changed},
        )
    return level


@transaction.atomic
def delete_level(level: SponsorLevel, *, actor: Actor) -> None:
    ensure_editable(level.edition)
    if level.sponsors.exists():
        raise RuleViolation(
            _("Niveau attribué à des partenaires : changez-leur de niveau d'abord."),
            code=ErrorCode.IN_USE,
        )
    record(
        "sponsor_level.deleted",
        actor=actor,
        edition=level.edition,
        obj=level,
        before=_level_snapshot(level),
    )
    level.delete()


# --- Partenaires ----------------------------------------------------------------------------------


def _clean_sponsor(
    edition: Edition, data: Mapping[str, Any], *, sponsor: Sponsor | None
) -> dict[str, Any]:
    _check_unknown(data, SPONSOR_FIELDS)
    errors: dict[str, list] = {}
    clean = _texts(data, errors)
    clean.update(_position(data, errors))
    if (sponsor is None or "name" in clean) and not clean.get("name"):
        errors["name"] = [_("Nom obligatoire.")]
    if "website" in data:
        website = (data["website"] or "").strip()
        if website:
            try:
                URLValidator(schemes=("http", "https"))(website)
            except ValidationError:
                errors["website"] = [_("Adresse web (http ou https) attendue.")]
        clean["website"] = website
    if "contact_email" in data:
        email = (data["contact_email"] or "").strip()
        if email:
            try:
                EmailValidator()(email)
            except ValidationError:
                errors["contact_email"] = [_("Adresse e-mail invalide.")]
        clean["contact_email"] = email
    if "level" in data:
        value = data["level"]
        if value in (None, ""):
            clean["level"] = None
        else:
            level_id = value.pk if isinstance(value, SponsorLevel) else value
            level = SponsorLevel.objects.filter(pk=level_id, edition=edition).first()
            if level is None:
                errors["level"] = [_("Niveau d'une autre édition.")]
            clean["level"] = level
    if "status" in data:
        if data["status"] not in SponsorStatus.values:
            errors["status"] = [_("Statut inconnu.")]
        clean["status"] = data["status"]
    if "published" in data:
        clean["published"] = bool(data["published"])
    for name in ("agreed_amount", "received_amount"):
        if name in data:
            clean[name] = _amount(edition, name, data[name], errors)
    if "received_on" in data:
        received_on = data["received_on"]
        if received_on is not None and not isinstance(received_on, dt.date):
            errors["received_on"] = [_("Date attendue.")]
        clean["received_on"] = received_on
    if errors:
        raise Invalid(fields=errors)
    # Contribution reçue : montant et date obligatoires (cohérence avec le budget).
    status = clean.get("status", sponsor.status if sponsor else SponsorStatus.PROSPECT)
    received = clean.get("received_amount", sponsor.received_amount if sponsor else None)
    received_on = clean.get("received_on", sponsor.received_on if sponsor else None)
    if status == SponsorStatus.RECEIVED and (not received or received_on is None):
        raise Invalid(fields={"received_amount": [_("Montant reçu et date obligatoires.")]})
    return clean


def _public_snapshot(sponsor: Sponsor) -> dict[str, Any]:
    values = {name: _value(getattr(sponsor, name)) for name in Sponsor.PUBLIC_FIELDS}
    values["level"] = sponsor.level_id
    return mask_emails(values)


def _private_snapshot(sponsor: Sponsor) -> dict[str, Any]:
    return mask_emails({name: _value(getattr(sponsor, name)) for name in Sponsor.PRIVATE_FIELDS})


def _copy_benefits(sponsor: Sponsor) -> None:
    """Contreparties du niveau ajoutées à la fiche (celles déjà présentes sont gardées)."""
    if sponsor.level is None:
        return
    existing = set(sponsor.benefits.values_list("label", flat=True))
    lines = [line.strip("-• \t") for line in sponsor.level.benefits_fr.splitlines()]
    start = sponsor.benefits.count()
    for offset, label in enumerate(line for line in lines if line and line not in existing):
        SponsorBenefit.objects.create(sponsor=sponsor, label=label[:200], position=start + offset)


@transaction.atomic
def create_sponsor(edition: Edition, data: Mapping[str, Any], *, actor: Actor) -> Sponsor:
    ensure_editable(edition)
    sponsor = Sponsor.objects.create(edition=edition, **_clean_sponsor(edition, data, sponsor=None))
    _copy_benefits(sponsor)
    record(
        "sponsor.created",
        actor=actor,
        edition=edition,
        obj=sponsor,
        after={
            **_public_snapshot(sponsor),
            **_private_snapshot(sponsor),
            "public": sponsor.published,
        },
    )
    return sponsor


@transaction.atomic
def update_sponsor(sponsor: Sponsor, data: Mapping[str, Any], *, actor: Actor) -> Sponsor:
    ensure_editable(sponsor.edition)
    sponsor = (
        Sponsor.objects.select_for_update().select_related("edition", "logo").get(pk=sponsor.pk)
    )
    clean = _clean_sponsor(sponsor.edition, data, sponsor=sponsor)
    before = {**_public_snapshot(sponsor), **_private_snapshot(sponsor)}
    contact_before = [getattr(sponsor, name) for name in Sponsor.CONTACT_FIELDS]
    previous_level = sponsor.level_id
    was_published = sponsor.published
    for name, value in clean.items():
        setattr(sponsor, name, value)
    sponsor.save()
    if sponsor.level_id != previous_level:
        _copy_benefits(sponsor)
    if sponsor.logo is not None and sponsor.logo.published != sponsor.published:
        sponsor.logo.published = sponsor.published
        sponsor.logo.save(update_fields=["published", "updated_at"])
    after = {**_public_snapshot(sponsor), **_private_snapshot(sponsor)}
    changed = [name for name in after if after[name] != before[name]]
    contact_changed = contact_before != [getattr(sponsor, name) for name in Sponsor.CONTACT_FIELDS]
    if changed or contact_changed:
        public = (was_published or sponsor.published) and any(
            name in Sponsor.PUBLIC_FIELDS for name in changed
        )
        record(
            "sponsor.updated",
            actor=actor,
            edition=sponsor.edition,
            obj=sponsor,
            before={name: before[name] for name in changed},
            after={
                **{name: after[name] for name in changed},
                "contact_changed": contact_changed,
                "public": public,
            },
        )
    return sponsor


@transaction.atomic
def delete_sponsor(sponsor: Sponsor, *, actor: Actor) -> None:
    ensure_editable(sponsor.edition)
    sponsor = (
        Sponsor.objects.select_for_update().select_related("edition", "logo").get(pk=sponsor.pk)
    )
    logo = sponsor.logo
    record(
        "sponsor.deleted",
        actor=actor,
        edition=sponsor.edition,
        obj=sponsor,
        before={**_public_snapshot(sponsor), **_private_snapshot(sponsor)},
        after={"public": sponsor.published},
    )
    sponsor.benefits.all().delete()
    sponsor.delete()
    if logo is not None:
        public_files.delete(logo)


@transaction.atomic
def set_logo(sponsor: Sponsor, *, data: bytes | None, name: str = "", actor: Actor) -> Sponsor:
    """Dépose (ou retire, ``data`` nul) le logo : image publique de nature ``logo``."""
    ensure_editable(sponsor.edition)
    sponsor = (
        Sponsor.objects.select_for_update().select_related("edition", "logo").get(pk=sponsor.pk)
    )
    previous = sponsor.logo
    sponsor.logo = None
    if data is not None:
        sponsor.logo = public_files.store(
            data=data,
            name=name,
            kind=PublicFileKind.LOGO,
            edition=sponsor.edition,
            title_fr=sponsor.name,
            title_en=sponsor.name,
            published=sponsor.published,
        )
    sponsor.save(update_fields=["logo", "updated_at"])
    if previous is not None:
        public_files.delete(previous)
    record(
        "sponsor.logo_changed",
        actor=actor,
        edition=sponsor.edition,
        obj=sponsor,
        after={
            "logo": str(sponsor.logo.uuid) if sponsor.logo else None,
            "public": sponsor.published,
        },
    )
    return sponsor


# --- Contreparties --------------------------------------------------------------------------------


@transaction.atomic
def add_benefit(sponsor: Sponsor, label: str, *, actor: Actor) -> SponsorBenefit:
    ensure_editable(sponsor.edition)
    text = (label or "").strip()
    if not text or len(text) > 200:
        raise Invalid(fields={"label": [_("Contrepartie de 1 à 200 caractères.")]})
    benefit = SponsorBenefit.objects.create(
        sponsor=sponsor, label=text, position=sponsor.benefits.count()
    )
    record("sponsor.benefit_added", actor=actor, edition=sponsor.edition, obj=sponsor)
    return benefit


@transaction.atomic
def mark_benefit(
    benefit: SponsorBenefit, delivered_on: dt.date | None, *, actor: Actor
) -> SponsorBenefit:
    ensure_editable(benefit.sponsor.edition)
    benefit.delivered_on = delivered_on
    benefit.save(update_fields=["delivered_on", "updated_at"])
    record(
        "sponsor.benefit_marked",
        actor=actor,
        edition=benefit.sponsor.edition,
        obj=benefit.sponsor,
        after=mask_emails({"label": benefit.label, "delivered_on": _value(delivered_on)}),
    )
    return benefit


@transaction.atomic
def remove_benefit(benefit: SponsorBenefit, *, actor: Actor) -> None:
    ensure_editable(benefit.sponsor.edition)
    record(
        "sponsor.benefit_removed",
        actor=actor,
        edition=benefit.sponsor.edition,
        obj=benefit.sponsor,
        before=mask_emails({"label": benefit.label}),
    )
    benefit.delete()


# --- Lectures -------------------------------------------------------------------------------------


def received_total(edition: Edition) -> Decimal:
    """Contributions reçues (réalisé de la ligne « partenariats » du budget, N4)."""
    total = (
        Sponsor.objects.filter(edition=edition)
        .exclude(status=SponsorStatus.DECLINED)
        .aggregate(total=Sum("received_amount"))["total"]
    )
    return total or ZERO


def totals(edition: Edition) -> dict[str, Any]:
    """Convenu et reçu (hors refus), nombre de partenaires par statut."""
    rows = Sponsor.objects.filter(edition=edition)
    active = rows.exclude(status=SponsorStatus.DECLINED)
    return {
        "currency": _currency(edition),
        "agreed": active.aggregate(total=Sum("agreed_amount"))["total"] or ZERO,
        "received": received_total(edition),
        "by_status": {
            status: rows.filter(status=status).count() for status in SponsorStatus.values
        },
    }


def public_page(edition: Edition) -> dict[str, Any]:
    """Page « Partenaires » : niveaux dans l'ordre, partenaires publiés seulement."""
    from apps.portal.services import public_file_url

    sponsors = (
        Sponsor.objects.filter(edition=edition, published=True)
        .select_related("logo", "level")
        .order_by("position", "id")
    )

    def card(sponsor: Sponsor) -> dict[str, Any]:
        logo = sponsor.logo
        return {
            "name": sponsor.name,
            "website": sponsor.website,
            "description_fr": sponsor.description_fr,
            "description_en": sponsor.description_en,
            "logo_url": public_file_url(logo) if logo is not None and logo.published else "",
            "logo_width": logo.width if logo else None,
            "logo_height": logo.height if logo else None,
        }

    levels = []
    for level in SponsorLevel.objects.filter(edition=edition).order_by("position", "id"):
        cards = [card(sponsor) for sponsor in sponsors if sponsor.level_id == level.pk]
        if cards:
            levels.append(
                {
                    "name_fr": level.name_fr,
                    "name_en": level.name_en,
                    "logo_size": level.logo_size,
                    "sponsors": cards,
                }
            )
    others = [card(sponsor) for sponsor in sponsors if sponsor.level_id is None]
    return {"levels": levels, "others": others}
