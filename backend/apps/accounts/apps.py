from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Comptes"

    def ready(self) -> None:
        from apps.accounts import receivers  # noqa: F401  (branche les récepteurs de signaux)
        from apps.accounts.notifications import register_account_templates
        from apps.accounts.services.invitations import (
            expire_due_invitations,
            register_invitation_templates,
        )
        from apps.accounts.services.mfa import register_mfa_templates
        from apps.accounts.services.roles import register_role_templates
        from apps.core.retention import register_retention_task

        register_account_templates()
        register_role_templates()
        register_invitation_templates()
        register_mfa_templates()
        # Changement d'état (et non purge) : appliqué à chaque passage de cleanup (§8.4).
        register_retention_task(
            "accounts.expire_invitations", expire_due_invitations, security=True
        )
