from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    verbose_name = "Socle"

    def ready(self) -> None:
        # Enregistre les extensions drf-spectacular (authentification par session).
        from apps.core import schema  # noqa: F401
        from apps.core.integrity import (
            check_cache_size,
            check_failed_jobs,
            register_integrity_check,
        )
        from apps.core.personal_data import register_personal_data
        from apps.core.personal_data_handlers import anonymize_audit, export_audit
        from apps.core.retention import (
            purge_audit_network,
            purge_audit_rows,
            purge_finished_jobs,
            register_retention_task,
        )

        register_retention_task("core.finished_jobs", purge_finished_jobs)
        register_retention_task("core.audit_network", purge_audit_network)
        register_retention_task("core.audit_rows", purge_audit_rows)
        register_integrity_check("core.cache_size", check_cache_size)
        register_integrity_check("core.failed_jobs", check_failed_jobs)
        register_personal_data(
            "core.audit",
            models=("core.AuditLog",),
            export=export_audit,
            anonymize=anonymize_audit,
        )
