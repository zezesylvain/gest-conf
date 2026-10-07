from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    name = "apps.communications"
    label = "communications"
    verbose_name = "Communications"

    def ready(self) -> None:
        # Enregistre le gestionnaire de la tâche « communications.send_email », les
        # gabarits d'e-mails et les règles de conservation du registre d'envoi.
        from apps.communications import retention, services  # noqa: F401
