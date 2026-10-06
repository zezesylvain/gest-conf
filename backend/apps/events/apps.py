from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    verbose_name = "Jour J et attestations"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.core.retention import register_retention_task
        from apps.events import integrity
        from apps.events.personal_data import register_events_personal_data
        from apps.events.services import signatures

        register_events_personal_data()
        register_integrity_check("events.checkins", integrity.check_checkins)
        register_retention_task(
            "events.orphan_signatures",
            signatures.IMAGES.purge_task(signatures.known_images),
            security=True,
        )
