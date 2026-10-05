"""Révoque un rôle par commande (motif obligatoire). Seule voie pour le dernier ADMIN."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.accounts.models import User, UserRole
from apps.accounts.roles import OcFunction, Role
from apps.accounts.services.roles import revoke_role
from apps.core.errors import DomainError
from apps.core.management.base import command_actor


class Command(BaseCommand):
    help = "Révoque un rôle d'un compte dans une édition."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--edition", required=True, help="Code de l'édition.")
        parser.add_argument("--role", required=True, choices=Role.values)
        parser.add_argument("--oc-function", default="", choices=OcFunction.values)
        parser.add_argument("--reason", required=True)

    def handle(self, *args: Any, **options: Any) -> None:
        user = User.objects.filter(email__iexact=options["email"].strip()).first()
        user_role = (
            UserRole.objects.filter(
                user=user,
                edition__code=options["edition"],
                role=options["role"],
                oc_function=options["oc_function"],
            ).first()
            if user
            else None
        )
        if user_role is None:
            raise CommandError("Rôle introuvable.")
        try:
            revoke_role(user_role=user_role, actor=command_actor(), reason=options["reason"])
        except DomainError as exc:
            raise CommandError(f"{exc.message} {exc.fields}") from exc
        self.stdout.write(f"Rôle {user_role.role} révoqué (#{user_role.pk}).")
