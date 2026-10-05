"""Crée une édition et désigne son premier administrateur (D1, plan L1 §1.1, démo B).

``--admin-email`` : attribue le rôle ADMIN si un compte porte cette adresse **vérifiée**,
sinon envoie une invitation (sans invitant), que la personne acceptera après avoir créé
son compte et vérifié son adresse (RG-20).
"""

from typing import Any

from allauth.account.models import EmailAddress
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from apps.accounts.models import RoleSource
from apps.accounts.roles import Role
from apps.accounts.services.invitations import create_invitations
from apps.accounts.services.roles import grant_role
from apps.conferences.models import Conference
from apps.conferences.services import create_edition, set_current_edition
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Crée une édition (brouillon) et désigne son administrateur."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--conference", required=True, help="Slug de la conférence.")
        parser.add_argument("--code", required=True, help="Code court, ex. GC27.")
        parser.add_argument("--slug", required=True)
        parser.add_argument("--year", type=int, required=True)
        parser.add_argument("--title-fr", required=True)
        parser.add_argument("--title-en", default="")
        parser.add_argument("--timezone", default="Africa/Abidjan")
        parser.add_argument("--admin-email", help="Premier administrateur de l'édition.")
        parser.add_argument("--locale", default="fr", choices=["fr", "en"])
        parser.add_argument(
            "--current", action="store_true", help="Désigner comme édition courante."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        conference = Conference.objects.filter(slug=options["conference"]).first()
        if conference is None:
            raise CommandError("Conférence inconnue.")
        actor = command_actor()
        try:
            with transaction.atomic():
                edition = create_edition(
                    conference=conference,
                    actor=actor,
                    code=options["code"],
                    slug=options["slug"],
                    year=options["year"],
                    title_fr=options["title_fr"],
                    title_en=options["title_en"],
                    timezone=options["timezone"],
                )
                if options["current"]:
                    set_current_edition(conference, edition, actor=actor)
                message = self._designate_admin(edition, options, actor)
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Édition {edition.code} créée (#{edition.pk}). {message}")

    def _designate_admin(self, edition, options, actor) -> str:
        email = (options.get("admin_email") or "").strip().lower()
        if not email:
            return "Aucun administrateur désigné."
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
            edition=edition,
            emails=[email],
            role=Role.ADMIN,
            actor=actor,
            access=None,
            locale=options["locale"],
        )
        return "Invitation ADMIN envoyée (aucun compte vérifié pour cette adresse)."
