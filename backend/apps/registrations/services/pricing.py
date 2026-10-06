"""Tarification des inscriptions (plan L6, J2 à J4).

- **Catalogue** (``pricing.write``) : catégories, grille de tarifs (par catégorie, période
  et zone), options à quota, codes promo. Écritures journalisées ; codes non modifiables après
  création (ils sont recopiés dans les lignes des inscriptions) ; un élément utilisé ne se
  supprime pas, il se désactive.
- **Calcul du prix** (``quote``) : par le serveur seul, en ``Decimal`` ; le navigateur
  n'envoie que des choix (codes).
- **Réservations** : places d'options et utilisations de codes promo, sous verrou de ligne,
  dans la transaction de la commande (L6.3).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.services.roles import ensure_editable
from apps.conferences.models import Edition, EditionStatus, KeyDateCode
from apps.conferences.services import key_date
from apps.core.actor import Actor
from apps.core.audit import record, snapshot
from apps.core.errors import ErrorCode, Invalid, RuleViolation
from apps.core.money import is_exact, quantize
from apps.registrations.models import (
    DiscountKind,
    DiscountScope,
    Fee,
    Period,
    PromoCode,
    Registration,
    RegistrationCategory,
    RegistrationOption,
    Zone,
)
from apps.registrations.services.settings import registration_settings, zone_for

CATEGORY_FIELDS = (
    "code",
    "label_fr",
    "label_en",
    "description_fr",
    "description_en",
    "requires_proof",
    "is_active",
    "position",
)
OPTION_FIELDS = (
    "code",
    "label_fr",
    "label_en",
    "description_fr",
    "description_en",
    "price_local",
    "price_international",
    "quota",
    "categories",
    "is_active",
    "position",
)
PROMO_FIELDS = (
    "code",
    "kind",
    "value",
    "scope",
    "categories",
    "max_uses",
    "valid_until",
    "is_active",
)

# --- Périodes et ouverture (J2) ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RegistrationWindow:
    """Dates clés des inscriptions (UTC) : ouverture, fin du tarif préférentiel, clôture."""

    opens_at: datetime | None
    early_bird_end: datetime | None
    closes_at: datetime | None


def registration_window(edition: Edition) -> RegistrationWindow:
    return RegistrationWindow(
        opens_at=key_date(edition, KeyDateCode.REGISTRATION_OPEN),
        early_bird_end=key_date(edition, KeyDateCode.EARLY_BIRD_END),
        closes_at=key_date(edition, KeyDateCode.REGISTRATION_CLOSE),
    )


def period_at(window: RegistrationWindow, at: datetime) -> str | None:
    """Période tarifaire à l'instant ``at`` : préférentiel avant ``early_bird_end``, normal
    avant ``registration_close``, puis sur place ; ``None`` avant l'ouverture."""
    if window.opens_at is None or at < window.opens_at:
        return None
    if window.early_bird_end is not None and at < window.early_bird_end:
        return Period.EARLY
    if window.closes_at is None or at < window.closes_at:
        return Period.REGULAR
    return Period.ONSITE


def is_open_online(edition: Edition, at: datetime | None = None) -> bool:
    """Inscription en ligne possible : édition publiée, entre ``registration_open`` (inclus)
    et ``registration_close`` (exclu). Après la clôture, seul le CO inscrit (sur place)."""
    if edition.status != EditionStatus.PUBLISHED:
        return False
    period = period_at(registration_window(edition), at or timezone.now())
    return period in (Period.EARLY, Period.REGULAR)


# --- Calcul du prix (J2 à J4) -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Line:
    kind: str  # « registration », « option » ou « discount »
    code: str
    label_fr: str
    label_en: str
    amount: Decimal

    def as_json(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "code": self.code,
            "label_fr": self.label_fr,
            "label_en": self.label_en,
            "amount": str(self.amount),
        }


@dataclass(frozen=True, slots=True)
class Quote:
    category: RegistrationCategory
    period: str
    zone: str
    currency: str
    lines: tuple[Line, ...]
    total: Decimal
    options: tuple[RegistrationOption, ...]
    promo_code: PromoCode | None


def normalize_code(value: str) -> str:
    return value.strip().upper()


def _category(edition: Edition, code: str) -> RegistrationCategory:
    category = RegistrationCategory.objects.filter(
        edition=edition, code=code, is_active=True
    ).first()
    if category is None:
        raise Invalid(fields={"category": [_("Catégorie inconnue.")]})
    return category


def _options(
    edition: Edition, codes: Sequence[str], category: RegistrationCategory
) -> list[RegistrationOption]:
    if len(set(codes)) != len(codes):
        raise Invalid(fields={"options": [_("Option choisie deux fois.")]})
    found = {
        option.code: option
        for option in RegistrationOption.objects.filter(
            edition=edition, code__in=codes, is_active=True
        ).prefetch_related("categories")
    }
    options = []
    for code in codes:
        option = found.get(code)
        if option is None:
            raise Invalid(fields={"options": [_("Option inconnue : %(code)s.") % {"code": code}]})
        allowed = list(option.categories.all())
        if allowed and category not in allowed:
            raise Invalid(
                fields={
                    "options": [
                        _("Option non proposée à cette catégorie : %(code)s.") % {"code": code}
                    ]
                }
            )
        options.append(option)
    return sorted(options, key=lambda option: (option.position, option.pk))


def has_uses_left(promo: PromoCode) -> bool:
    return promo.max_uses is None or promo.reserved_uses + promo.consumed_uses < promo.max_uses


def _promo(
    edition: Edition, code: str, category: RegistrationCategory, at: datetime
) -> PromoCode | None:
    code = normalize_code(code)
    if not code:
        return None
    promo = (
        PromoCode.objects.filter(edition=edition, code=code, is_active=True)
        .prefetch_related("categories")
        .first()
    )
    if promo is None or (promo.valid_until is not None and at >= promo.valid_until):
        raise Invalid(fields={"promo_code": [_("Code promo inconnu ou expiré.")]})
    targeted = list(promo.categories.all())
    if targeted and category not in targeted:
        raise Invalid(fields={"promo_code": [_("Code promo non valable pour cette catégorie.")]})
    if not has_uses_left(promo):
        raise RuleViolation(
            _("Ce code promo a atteint son nombre d'utilisations."),
            code=ErrorCode.PROMO_CODE_EXHAUSTED,
            fields={"promo_code": [_("Code promo épuisé.")]},
        )
    return promo


def discount_amount(promo: PromoCode, base: Decimal, currency: str) -> Decimal:
    """Remise, arrondie une fois à la décimale de la devise, jamais supérieure à la base."""
    if promo.kind == DiscountKind.PERCENT:
        value = quantize(base * promo.value / Decimal(100), currency)
    else:
        value = promo.value
    return min(value, base)


def quote(
    edition: Edition,
    *,
    category: str,
    options: Sequence[str] = (),
    promo_code: str = "",
    country: str = "",
    period: str | None = None,
    at: datetime | None = None,
) -> Quote:
    """Prix d'une inscription, calculé par le serveur seul.

    ``period`` force la période (inscription sur place par le CO) ; sinon elle découle des
    dates clés à l'instant ``at``. Zone d'après le pays (J2). Tarif absent pour la période et
    la zone : catégorie non proposée."""
    at = at or timezone.now()
    settings = registration_settings(edition)
    currency = settings.currency
    if period is None:
        period = period_at(registration_window(edition), at)
        if period is None:
            raise RuleViolation(
                _("Les inscriptions ne sont pas encore ouvertes."),
                code=ErrorCode.REGISTRATION_CLOSED,
            )
    zone = zone_for(edition, settings, country)
    chosen = _category(edition, category)
    fee = Fee.objects.filter(category=chosen, period=period, zone=zone).first()
    if fee is None:
        raise Invalid(
            fields={"category": [_("Catégorie non proposée pour cette période et cette zone.")]}
        )
    chosen_options = _options(edition, list(options), chosen)
    promo = _promo(edition, promo_code, chosen, at)

    registration_line = Line(
        "registration", chosen.code, chosen.label_fr, chosen.label_en or chosen.label_fr, fee.amount
    )
    option_lines = [
        Line(
            "option",
            option.code,
            option.label_fr,
            option.label_en or option.label_fr,
            option.price_local if zone == Zone.LOCAL else option.price_international,
        )
        for option in chosen_options
    ]
    lines = [registration_line, *option_lines]
    if promo is not None:
        base = registration_line.amount
        if promo.scope == DiscountScope.ALL:
            base += sum((line.amount for line in option_lines), Decimal(0))
        value = discount_amount(promo, base, currency)
        if value > 0:
            lines.append(
                Line(
                    "discount",
                    promo.code,
                    # Libellés figés dans les deux langues, indépendants de la requête.
                    f"Remise {promo.code}",
                    f"Discount {promo.code}",
                    -value,
                )
            )
    total = sum((line.amount for line in lines), Decimal(0))
    return Quote(
        category=chosen,
        period=period,
        zone=zone,
        currency=currency,
        lines=tuple(lines),
        total=total,
        options=tuple(chosen_options),
        promo_code=promo,
    )


# --- Réservations (J3, J4), dans la transaction de la commande ---------------------------------


def _require_atomic() -> None:
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("Réservation hors transaction.")


def reserve_options(options: Iterable[RegistrationOption]) -> None:
    """Une place par option, sous verrou de ligne (ordre des clés : pas d'interblocage)."""
    _require_atomic()
    ids = sorted({option.pk for option in options})
    for option in RegistrationOption.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
        if option.quota is not None and option.reserved >= option.quota:
            raise RuleViolation(
                _("Plus de place disponible pour cette option : %(code)s.") % {"code": option.code},
                code=ErrorCode.OPTION_FULL,
                fields={"options": [option.code]},
            )
        RegistrationOption.objects.filter(pk=option.pk).update(reserved=F("reserved") + 1)


def release_options(options: Iterable[RegistrationOption]) -> None:
    _require_atomic()
    ids = sorted({option.pk for option in options})
    for option in RegistrationOption.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
        if option.reserved > 0:
            RegistrationOption.objects.filter(pk=option.pk).update(reserved=F("reserved") - 1)


def reserve_promo(promo: PromoCode) -> None:
    """Réserve une utilisation (commande en attente), sous verrou de ligne."""
    _require_atomic()
    locked = PromoCode.objects.select_for_update().get(pk=promo.pk)
    if not has_uses_left(locked):
        raise RuleViolation(
            _("Ce code promo a atteint son nombre d'utilisations."),
            code=ErrorCode.PROMO_CODE_EXHAUSTED,
            fields={"promo_code": [_("Code promo épuisé.")]},
        )
    PromoCode.objects.filter(pk=promo.pk).update(reserved_uses=F("reserved_uses") + 1)


def consume_promo(promo: PromoCode) -> None:
    """Confirmation : l'utilisation réservée devient consommée."""
    _require_atomic()
    locked = PromoCode.objects.select_for_update().get(pk=promo.pk)
    if locked.reserved_uses > 0:
        PromoCode.objects.filter(pk=promo.pk).update(
            reserved_uses=F("reserved_uses") - 1, consumed_uses=F("consumed_uses") + 1
        )


def release_promo(promo: PromoCode) -> None:
    """Expiration ou annulation d'une commande en attente : l'utilisation est rendue."""
    _require_atomic()
    locked = PromoCode.objects.select_for_update().get(pk=promo.pk)
    if locked.reserved_uses > 0:
        PromoCode.objects.filter(pk=promo.pk).update(reserved_uses=F("reserved_uses") - 1)


# --- Catalogue (pricing.write) ------------------------------------------------------------------


def _editable(edition: Edition) -> Edition:
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    ensure_editable(edition)
    return edition


def _check_fields(data: Mapping[str, Any], allowed: Sequence[str], *, creating: bool) -> None:
    unknown = set(data) - set(allowed)
    if not creating and "code" in data:
        unknown.add("code")
    if unknown:
        raise Invalid(fields={name: [_("Champ non modifiable.")] for name in sorted(unknown)})


def _check_amount(edition: Edition, name: str, amount: Decimal | None) -> None:
    if amount is None:
        return
    currency = registration_settings(edition).currency
    if amount < 0:
        raise Invalid(fields={name: [_("Montant positif ou nul attendu.")]})
    if not is_exact(amount, currency):
        message = _("Trop de décimales pour la devise %(currency)s.") % {"currency": currency}
        raise Invalid(fields={name: [message]})


def _full_clean(instance, exclude: Sequence[str] = ()) -> None:
    try:
        instance.full_clean(exclude=list(exclude))
    except ValidationError as exc:
        raise Invalid(fields=exc.message_dict) from exc


def _in_use(message) -> RuleViolation:
    return RuleViolation(message, code=ErrorCode.IN_USE)


def _categories(edition: Edition, codes: Iterable[str]) -> list[RegistrationCategory]:
    codes = list(dict.fromkeys(codes))
    found = list(RegistrationCategory.objects.filter(edition=edition, code__in=codes))
    if len(found) != len(codes):
        raise Invalid(fields={"categories": [_("Catégorie inconnue.")]})
    return found


def _changed(instance, values: Mapping[str, Any]) -> list[str]:
    return [name for name, value in values.items() if getattr(instance, name) != value]


def _save_with_audit(instance, edition, values, action: str, actor: Actor) -> None:
    changed = _changed(instance, values)
    if not changed:
        return
    before = snapshot(instance)
    for name in changed:
        setattr(instance, name, values[name])
    _full_clean(instance, exclude=["edition", "category"])
    instance.save(update_fields=[*changed, "updated_at"])
    after = snapshot(instance)
    audited = [name for name in changed if name in before]
    record(
        action,
        actor=actor,
        edition=edition,
        obj=instance,
        before={name: before[name] for name in audited},
        after={name: after[name] for name in audited},
    )


@transaction.atomic
def create_category(edition: Edition, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, CATEGORY_FIELDS, creating=True)
    edition = _editable(edition)
    category = RegistrationCategory(edition=edition, **data)
    _full_clean(category)
    category.save()
    record(
        "registrations.category_created",
        actor=actor,
        edition=edition,
        obj=category,
        after=snapshot(category),
    )
    return category


@transaction.atomic
def update_category(category: RegistrationCategory, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, CATEGORY_FIELDS, creating=False)
    edition = _editable(category.edition)
    category = RegistrationCategory.objects.select_for_update().get(pk=category.pk)
    _save_with_audit(category, edition, data, "registrations.category_updated", actor)
    return category


@transaction.atomic
def delete_category(category: RegistrationCategory, *, actor: Actor) -> None:
    edition = _editable(category.edition)
    if Registration.objects.filter(category=category).exists():
        raise _in_use(_("Catégorie utilisée par des inscriptions : désactivez-la."))
    before = snapshot(category)
    Fee.objects.filter(category=category).delete()
    category.delete()
    record("registrations.category_deleted", actor=actor, edition=edition, before=before)


@transaction.atomic
def set_fees(
    category: RegistrationCategory, cells: Sequence[Mapping[str, Any]], *, actor: Actor
) -> list[Fee]:
    """Remplace la grille de la catégorie : une cellule par (période, zone), montant ou
    rien (cellule absente : combinaison non proposée). Les inscriptions déjà passées gardent
    leur prix figé."""
    edition = _editable(category.edition)
    category = RegistrationCategory.objects.select_for_update().get(pk=category.pk)
    wanted: dict[tuple[str, str], Decimal] = {}
    for cell in cells:
        key = (cell["period"], cell["zone"])
        if key in wanted:
            raise Invalid(fields={"fees": [_("Période et zone en double.")]})
        _check_amount(edition, "fees", cell["amount"])
        wanted[key] = cell["amount"]
    current = {(fee.period, fee.zone): fee for fee in Fee.objects.filter(category=category)}
    before = {f"{period}:{zone}": str(fee.amount) for (period, zone), fee in current.items()}
    for key, fee in current.items():
        if key not in wanted:
            fee.delete()
        elif fee.amount != wanted[key]:
            fee.amount = wanted[key]
            fee.save(update_fields=["amount", "updated_at"])
    for (period, zone), amount in wanted.items():
        if (period, zone) not in current:
            Fee.objects.create(category=category, period=period, zone=zone, amount=amount)
    fees = list(Fee.objects.filter(category=category).order_by("period", "zone"))
    after = {f"{fee.period}:{fee.zone}": str(fee.amount) for fee in fees}
    if before != after:
        record(
            "registrations.fees_changed",
            actor=actor,
            edition=edition,
            obj=category,
            before=before,
            after=after,
        )
    return fees


def _option_values(edition: Edition, data: Mapping[str, Any]) -> tuple[dict, list | None]:
    values = dict(data)
    categories = values.pop("categories", None)
    for name in ("price_local", "price_international"):
        if name in values:
            _check_amount(edition, name, values[name])
    return values, None if categories is None else _categories(edition, categories)


@transaction.atomic
def create_option(edition: Edition, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, OPTION_FIELDS, creating=True)
    edition = _editable(edition)
    values, categories = _option_values(edition, data)
    option = RegistrationOption(edition=edition, **values)
    _full_clean(option)
    option.save()
    if categories:
        option.categories.set(categories)
    record(
        "registrations.option_created",
        actor=actor,
        edition=edition,
        obj=option,
        after={**snapshot(option), "categories": sorted(c.code for c in categories or [])},
    )
    return option


@transaction.atomic
def update_option(option: RegistrationOption, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, OPTION_FIELDS, creating=False)
    edition = _editable(option.edition)
    option = RegistrationOption.objects.select_for_update().get(pk=option.pk)
    values, categories = _option_values(edition, data)
    quota = values.get("quota", option.quota)
    if quota is not None and quota < option.reserved:
        raise Invalid(
            fields={
                "quota": [
                    _("Au moins %(count)s places, déjà réservées.") % {"count": option.reserved}
                ]
            }
        )
    _save_with_audit(option, edition, values, "registrations.option_updated", actor)
    if categories is not None:
        before = sorted(category.code for category in option.categories.all())
        after = sorted(category.code for category in categories)
        if before != after:
            option.categories.set(categories)
            record(
                "registrations.option_updated",
                actor=actor,
                edition=edition,
                obj=option,
                before={"categories": before},
                after={"categories": after},
            )
    return option


@transaction.atomic
def delete_option(option: RegistrationOption, *, actor: Actor) -> None:
    edition = _editable(option.edition)
    option = RegistrationOption.objects.select_for_update().get(pk=option.pk)
    if option.reserved or Registration.objects.filter(options=option).exists():
        raise _in_use(_("Option choisie par des inscriptions : désactivez-la."))
    before = snapshot(option)
    option.categories.clear()
    option.delete()
    record("registrations.option_deleted", actor=actor, edition=edition, before=before)


def _promo_values(edition: Edition, data: Mapping[str, Any], promo: PromoCode | None):
    values = dict(data)
    categories = values.pop("categories", None)
    if "code" in values:
        values["code"] = normalize_code(values["code"])
        if not values["code"]:
            raise Invalid(fields={"code": [_("Code obligatoire.")]})
    kind = values.get("kind", promo.kind if promo else None)
    value = values.get("value", promo.value if promo else None)
    if value is not None:
        if value <= 0:
            raise Invalid(fields={"value": [_("Valeur strictement positive attendue.")]})
        if kind == DiscountKind.PERCENT and value > 100:
            raise Invalid(fields={"value": [_("Pourcentage de 100 au plus.")]})
        if kind == DiscountKind.AMOUNT:
            _check_amount(edition, "value", value)
    return values, None if categories is None else _categories(edition, categories)


@transaction.atomic
def create_promo_code(edition: Edition, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, PROMO_FIELDS, creating=True)
    edition = _editable(edition)
    values, categories = _promo_values(edition, data, None)
    if PromoCode.objects.filter(edition=edition, code=values.get("code", "")).exists():
        raise Invalid(fields={"code": [_("Code déjà utilisé dans cette édition.")]})
    promo = PromoCode(edition=edition, **values)
    _full_clean(promo)
    promo.save()
    if categories:
        promo.categories.set(categories)
    record(
        "registrations.promo_code_created",
        actor=actor,
        edition=edition,
        obj=promo,
        after={**snapshot(promo), "categories": sorted(c.code for c in categories or [])},
    )
    return promo


@transaction.atomic
def update_promo_code(promo: PromoCode, data: Mapping[str, Any], *, actor: Actor):
    _check_fields(data, PROMO_FIELDS, creating=False)
    edition = _editable(promo.edition)
    promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
    values, categories = _promo_values(edition, data, promo)
    max_uses = values.get("max_uses", promo.max_uses)
    used = promo.reserved_uses + promo.consumed_uses
    if max_uses is not None and max_uses < used:
        raise Invalid(
            fields={"max_uses": [_("Au moins %(count)s, déjà utilisées.") % {"count": used}]}
        )
    _save_with_audit(promo, edition, values, "registrations.promo_code_updated", actor)
    if categories is not None:
        before = sorted(category.code for category in promo.categories.all())
        after = sorted(category.code for category in categories)
        if before != after:
            promo.categories.set(categories)
            record(
                "registrations.promo_code_updated",
                actor=actor,
                edition=edition,
                obj=promo,
                before={"categories": before},
                after={"categories": after},
            )
    return promo


@transaction.atomic
def delete_promo_code(promo: PromoCode, *, actor: Actor) -> None:
    edition = _editable(promo.edition)
    promo = PromoCode.objects.select_for_update().get(pk=promo.pk)
    if promo.reserved_uses or promo.consumed_uses or promo.registrations.exists():
        raise _in_use(_("Code promo déjà utilisé : désactivez-le."))
    before = snapshot(promo)
    promo.categories.clear()
    promo.delete()
    record("registrations.promo_code_deleted", actor=actor, edition=edition, before=before)
