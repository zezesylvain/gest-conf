from django.apps import AppConfig


class ProgramConfig(AppConfig):
    name = "apps.program"
    verbose_name = "Programme"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.program import integrity
        from apps.program.personal_data import register_program_personal_data

        register_program_personal_data()
        register_integrity_check("program.slots", integrity.check_slots)
