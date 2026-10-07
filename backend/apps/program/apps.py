from django.apps import AppConfig


class ProgramConfig(AppConfig):
    name = "apps.program"
    verbose_name = "Programme"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.portal.services import register_route_provider
        from apps.program import integrity
        from apps.program.notifications import register_program_templates
        from apps.program.personal_data import register_program_personal_data
        from apps.program.services import presentation
        from apps.program.services.publication import public_paths
        from apps.submissions import workflow

        register_program_personal_data()
        register_program_templates()
        register_integrity_check("program.slots", integrity.check_slots)
        register_integrity_check("program.publication", integrity.check_publication)
        workflow.register_guard(presentation.guard_confirmation)
        workflow.register_effect(presentation.on_transition)
        # Pages du programme public à pré-rendre et à contrôler au build (I7).
        register_route_provider(public_paths)
        # Segments des envois groupés (plan L8, N11), déclarés auprès de communications.
        from apps.program.segments import register_program_segments

        register_program_segments()
