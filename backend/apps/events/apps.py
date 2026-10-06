from django.apps import AppConfig


class EventsConfig(AppConfig):
    name = "apps.events"
    verbose_name = "Jour J et attestations"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.core.retention import register_retention_task
        from apps.events import integrity
        from apps.events.notifications import register_events_templates
        from apps.events.personal_data import register_events_personal_data
        from apps.events.services import certificates, letters, signatures

        register_events_personal_data()
        register_events_templates()
        register_integrity_check("events.checkins", integrity.check_checkins)
        register_integrity_check("events.certificate_files", integrity.check_certificate_files)
        register_integrity_check("events.letter_files", integrity.check_letter_files)
        for name, store, known in (
            ("events.orphan_certificates", certificates.PDFS, certificates.known_files),
            ("events.orphan_headers", certificates.HEADERS, certificates.known_headers),
            ("events.orphan_signing_keys", certificates.KEYS, certificates.known_keys),
            ("events.orphan_letters", letters.PDFS, letters.known_files),
        ):
            register_retention_task(name, store.purge_task(known), security=True)
        # K14 (validée) : numéros de passeport effacés 30 jours après l'édition.
        register_retention_task(
            "events.passport_numbers", letters.erase_passport_numbers, security=True
        )
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
