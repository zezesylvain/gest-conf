from django.apps import AppConfig


class CommunicationsConfig(AppConfig):
    name = "apps.communications"
    label = "communications"
    verbose_name = "Communications"

    def ready(self) -> None:
        from apps.communications import jobs  # noqa: F401  (enregistre les tâches)
        from apps.communications.notifications import (
            anonymize_notifications,
            export_notifications,
            purge_old_notifications,
        )
        from apps.communications.personal_data import (
            anonymize_emails,
            export_emails,
            purge_old_metadata,
        )
        from apps.communications.services import (
            purge_old_bodies,
            purge_unsent_sensitive_bodies,
            register_email_template,
        )
        from apps.core.personal_data import register_personal_data
        from apps.core.retention import register_retention_task

        register_retention_task(
            "communications.unsent_sensitive_bodies", purge_unsent_sensitive_bodies, security=True
        )
        register_retention_task("communications.old_bodies", purge_old_bodies)
        register_retention_task("communications.old_metadata", purge_old_metadata)
        register_retention_task("communications.old_notifications", purge_old_notifications)
        register_personal_data(
            "communications.notifications",
            models=("communications.Notification",),
            export=export_notifications,
            anonymize=anonymize_notifications,
        )
        register_personal_data(
            "communications.outbox",
            models=("communications.OutboxEmail",),
            export=export_emails,
            anonymize=anonymize_emails,
        )
        # E-mail de contrôle de la chaîne d'envoi (manage.py send_test_email, jalon J-tech).
        register_email_template("communications/email/test")
        # Annonces envoyées à un segment (plan L8, N11) ; ni sensible ni voie rapide.
        register_email_template("communications/email/announcement")
        from apps.communications.personal_data import (
            anonymize_announcements,
            export_announcements,
        )

        register_personal_data(
            "communications.announcements",
            models=(
                "communications.Announcement",
                "communications.AnnouncementDelivery",
                "communications.AnnouncementOptOut",
            ),
            export=export_announcements,
            anonymize=anonymize_announcements,
        )
