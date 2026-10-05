from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "Comptes"

    def ready(self) -> None:
        from apps.accounts import receivers  # noqa: F401  (branche les récepteurs de signaux)
        from apps.accounts.notifications import register_account_templates

        register_account_templates()
