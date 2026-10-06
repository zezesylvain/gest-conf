from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "apps.payments"
    verbose_name = "Paiements et facturation"

    def ready(self) -> None:
        from apps.payments.personal_data import register_payments_personal_data

        register_payments_personal_data()
