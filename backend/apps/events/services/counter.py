"""Inscription au comptoir d'une personne sans compte (plan L7, K13 ; reporté de L6).

Le CO (``registrations.manage``) saisit l'adresse, le nom, l'institution et le pays :

- adresse **inconnue** : compte créé **sans mot de passe** (inutilisable), adresse non
  vérifiée, profil minimal ; journal ``registrations.counter_created``. Personne ne peut s'y
  connecter avant d'avoir défini son mot de passe par le lien envoyé (réinitialisation
  d'allauth, ``send_password_setup``), puis vérifié son adresse ;
- adresse **connue** (compte actif) : on rattache l'inscription au compte existant, sans
  toucher à son profil ; compte désactivé ou anonymisé : refus.

Puis inscription par le CO (tarif « sur place » après la clôture, J2) et, si la personne
règle au comptoir, paiement manuel « sur place » (J7) : l'inscription est confirmée et son
badge s'imprime.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from allauth.account.models import EmailAddress
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Profile, User
from apps.accounts.validators import validate_country
from apps.core.audit import mask_email, record
from apps.core.errors import Invalid
from apps.registrations.models import PaymentMethod, Registration, RegistrationStatus
from apps.registrations.services import orders

if TYPE_CHECKING:
    from apps.conferences.models import Edition
    from apps.core.actor import Actor


@dataclass(frozen=True, slots=True)
class CounterResult:
    registration: Registration
    account_created: bool


def _account(edition: Edition, data: dict[str, Any], actor: Actor) -> tuple[User, bool]:
    email = User.objects.normalize_email(data["email"].strip())
    existing = User.objects.filter(email__iexact=email).first()
    if existing is not None:
        if not existing.is_active or existing.anonymized_at is not None:
            raise Invalid(fields={"email": [_("Compte désactivé : inscription impossible.")]})
        return existing, False
    first_name, last_name = data["first_name"].strip(), data["last_name"].strip()
    if not first_name or not last_name:
        raise Invalid(
            fields={
                name: [_("Champ obligatoire.")]
                for name, value in (("first_name", first_name), ("last_name", last_name))
                if not value
            }
        )
    country = data.get("country", "")
    if country:
        try:
            validate_country(country)
        except ValidationError as error:
            raise Invalid(fields={"country": [_("Code pays ISO 3166-1 inconnu.")]}) from error
    user = User.objects.create_user(email=email, password=None)
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    Profile.objects.create(
        user=user,
        first_name=first_name,
        last_name=last_name,
        institution=data.get("institution", "").strip(),
        country=country,
    )
    record(
        "registrations.counter_created",
        actor=actor,
        edition=edition,
        obj=user,
        after={"email_masked": mask_email(email)},
    )
    return user, True


@transaction.atomic
def counter_registration(edition: Edition, data: dict[str, Any], *, actor: Actor) -> CounterResult:
    from apps.payments.services.manual import record_manual_payment

    user, created = _account(edition, data, actor)
    registration = orders.place_order(
        edition,
        user,
        category=data["category"],
        options=data.get("options", ()),
        method=PaymentMethod.ONSITE,
        actor=actor,
        by_committee=True,
    )
    if data.get("paid") and registration.status == RegistrationStatus.PENDING:
        record_manual_payment(
            registration,
            method=PaymentMethod.ONSITE,
            amount=registration.total,
            reference=str(_("Comptoir")),
            received_on=timezone.localdate(),
            actor=actor,
        )
        registration.refresh_from_db()
    return CounterResult(registration, created)


def send_password_setup(request, user: User) -> None:
    """Lien de définition du mot de passe (réinitialisation d'allauth), mis en file."""
    from allauth.account.forms import ResetPasswordForm

    form = ResetPasswordForm(data={"email": user.email})
    if form.is_valid():
        form.save(request)
