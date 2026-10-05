from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self) -> None:
        # Enregistre les extensions drf-spectacular (authentification par session).
        from apps.core import schema  # noqa: F401
        from apps.core.retention import purge_finished_jobs, register_retention_task

        register_retention_task("core.finished_jobs", purge_finished_jobs)
