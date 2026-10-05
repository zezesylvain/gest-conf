"""Attribue un rôle par commande (opérateur, D1 ; matrice §5.5 : « Opérateur : oui »).

Le compte doit exister. Pour une personne sans compte, utiliser une invitation.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import RoleSource, User
from apps.accounts.roles import OcFunction, Role
from apps.accounts.services.roles import grant_role
from apps.conferences.models import Edition
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Attribue un rôle à un compte dans une édition."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--edition", required=True, help="Code de l'édition.")
        parser.add_argument("--role", required=True, choices=Role.values)
        parser.add_argument("--oc-function", default="", choices=OcFunction.values)
        parser.add_argument("--reason", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        edition = Edition.objects.filter(code=options["edition"]).first()
        if user is None or edition is None:
            raise CommandError("Compte ou édition inconnu.")
        try:
            user_role = grant_role(
                user=user,
                edition=edition,
                role=options["role"],
                oc_function=options["oc_function"],
                actor=command_actor(),
                source=RoleSource.COMMAND,
                reason=options["reason"],
            )
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Rôle {user_role.role} actif (#{user_role.pk}).")
