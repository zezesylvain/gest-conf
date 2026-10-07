from django.apps import AppConfig


class RegistrationsConfig(AppConfig):
    name = "apps.registrations"
    verbose_name = "Inscriptions"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.core.retention import register_retention_task
        from apps.program.services.planning import register_registered_people
        from apps.registrations import integrity
        from apps.registrations.notifications import register_registration_templates
        from apps.registrations.personal_data import register_registrations_personal_data
        from apps.registrations.services import orders

        register_registrations_personal_data()
        register_registration_templates()
        register_retention_task(
            "registrations.orphan_proofs",
            orders.PROOFS.purge_task(orders.known_proofs),
            security=True,
        )
        register_integrity_check("registrations.totals", integrity.check_totals)
        register_integrity_check("registrations.reservations", integrity.check_reservations)
        # RG-11 (J10) : le planificateur reconnaît les présentateurs inscrits.
        register_registered_people(orders.registered_people)
        # Segments des envois groupés (plan L8, N11), déclarés auprès de communications.
        from apps.registrations.segments import register_registrations_segments

        register_registrations_segments()
