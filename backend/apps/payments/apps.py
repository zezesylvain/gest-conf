from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "apps.payments"
    verbose_name = "Paiements et facturation"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.core.retention import register_retention_task
        from apps.payments import integrity
        from apps.payments.personal_data import register_payments_personal_data
        from apps.payments.services import documents, online
        from apps.registrations.services.orders import register_expiry_check, register_order_effect

        register_payments_personal_data()
        register_order_effect(documents.proforma_on_order)
        register_expiry_check(online.postpone_expiry)
        register_retention_task(
            "payments.orphan_files",
            documents.DOCUMENTS.purge_task(documents.known_documents),
            security=True,
        )
        register_integrity_check("billing.series", integrity.check_series)
        register_integrity_check("billing.files", integrity.check_files)
