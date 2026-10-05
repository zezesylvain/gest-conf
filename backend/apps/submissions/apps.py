from django.apps import AppConfig


class SubmissionsConfig(AppConfig):
    name = "apps.submissions"
    verbose_name = "Soumissions"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.submissions import (
            integrity,
            notifications,
            receivers,  # noqa: F401
            workflow,
        )
        from apps.submissions.personal_data import register_submissions_personal_data

        register_submissions_personal_data()
        notifications.register_submission_templates()
        workflow.register_effect(notifications.on_transition)
        register_integrity_check("submissions.current_files", integrity.check_current_files)
        register_integrity_check("submissions.missing_files", integrity.check_missing_files)
        register_integrity_check("submissions.references", integrity.check_reference_sequence)
        from apps.core.retention import register_retention_task
        from apps.submissions.storage import purge_orphan_files

        # Fichiers écrits puis transaction annulée : toujours purgés (sécurité, comme L2).
        register_retention_task("submissions.orphan_files", purge_orphan_files, security=True)
