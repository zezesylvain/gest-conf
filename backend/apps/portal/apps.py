from django.apps import AppConfig


class PortalConfig(AppConfig):
    name = "apps.portal"
    verbose_name = "Portail public"

    def ready(self) -> None:
        from apps.portal import receivers  # noqa: F401
