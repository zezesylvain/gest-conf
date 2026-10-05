from django.apps import AppConfig


class SubmissionsConfig(AppConfig):
    name = "apps.submissions"
    verbose_name = "Soumissions"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.submissions import (
            integrity,
            receivers,  # noqa: F401
        )
        from apps.submissions.personal_data import register_submissions_personal_data

        register_submissions_personal_data()
        register_integrity_check("submissions.current_files", integrity.check_current_files)
        register_integrity_check("submissions.missing_files", integrity.check_missing_files)
        register_integrity_check("submissions.references", integrity.check_reference_sequence)
