from django.apps import AppConfig


class SponsorsConfig(AppConfig):
    name = "apps.sponsors"
    verbose_name = "Partenaires"

    def ready(self) -> None:
        from django.utils.translation import gettext_lazy as _

        from apps.core.integrity import register_integrity_check
        from apps.core.personal_data import exempt_model
        from apps.logistics.models import BudgetCategory, BudgetKind, BudgetSource
        from apps.logistics.services.budget import register_computed_source
        from apps.sponsors import integrity, services

        # N4 : le réalisé de la ligne « partenariats » du budget est le total reçu.
        register_computed_source(
            BudgetSource.SPONSORS,
            BudgetKind.INCOME,
            BudgetCategory.SPONSORSHIP,
            _("Partenariats (contributions reçues)"),
            services.received_total,
        )
        register_integrity_check("sponsors.contributions", integrity.check_contributions)
        # Le contact d'un partenaire n'est pas un compte de la plateforme : jamais publié ni
        # journalisé, il est corrigé ou effacé avec la fiche du partenaire (N15).
        exempt_model(
            "sponsors.Sponsor",
            "Contact d'un partenaire (organisation), sans compte : jamais publié ni journalisé, "
            "corrigé ou effacé avec la fiche ; pas de demande d'accès par compte possible.",
        )
