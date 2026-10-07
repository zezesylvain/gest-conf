from django.apps import AppConfig


class LogisticsConfig(AppConfig):
    name = "apps.logistics"
    verbose_name = "Logistique et organisation"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.core.retention import register_retention_task
        from apps.logistics import integrity
        from apps.logistics.notifications import register_logistics_templates
        from apps.logistics.personal_data import register_logistics_personal_data
        from apps.logistics.services import budget, tasks

        register_logistics_templates()
        register_logistics_personal_data()
        register_integrity_check("logistics.task_attachments", integrity.check_task_attachments)
        register_integrity_check("logistics.budget_proofs", integrity.check_budget_proofs)
        register_retention_task(
            "logistics.orphan_task_attachments",
            tasks.ATTACHMENTS.purge_task(tasks.known_attachments),
            security=True,
        )
        register_retention_task(
            "logistics.orphan_budget_proofs",
            budget.PROOFS.purge_task(budget.known_proofs),
            security=True,
        )
        # RG-23, N15 : fiches de venue et régimes effacés 30 jours après l'édition.
        from apps.logistics.services import dietary, visits

        register_retention_task("logistics.dietary", dietary.erase_after_edition, security=True)
        register_retention_task("logistics.visits", visits.erase_after_edition, security=True)
