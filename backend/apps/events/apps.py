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
        # K8 : le président de séance marque « présentée » une communication de sa session ;
        # K7 : une session émargée ne se supprime plus du brouillon.
        from apps.events.services import attendance
        from apps.program.services.planning import register_session_guard
        from apps.submissions import workflow
        from apps.submissions.models import SubmissionStatus

        workflow.register_actor_grant(
            SubmissionStatus.SCHEDULED, SubmissionStatus.PRESENTED, attendance.chair_grant
        )
        register_session_guard(attendance.session_guard)
        register_retention_task(
            "events.orphan_signatures",
            signatures.IMAGES.purge_task(signatures.known_images),
            security=True,
        )
