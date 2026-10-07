from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self) -> None:
        # Enregistre les extensions drf-spectacular (authentification par session) et les
        # règles de conservation du socle (cache, sessions, audit, tâches terminées).
        from apps.core import retention, schema  # noqa: F401
