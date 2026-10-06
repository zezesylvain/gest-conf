from django.apps import AppConfig


class RegistrationsConfig(AppConfig):
    name = "apps.registrations"
    verbose_name = "Inscriptions"

    def ready(self) -> None:
        from apps.registrations.personal_data import register_registrations_personal_data

        register_registrations_personal_data()
