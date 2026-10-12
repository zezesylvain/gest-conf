from django.apps import AppConfig


class QaConfig(AppConfig):
    """Outillage de recette (plan L9) : données fictives de charge et de démonstration,
    sessions du test de charge. Aucun modèle ; dépend des applications métier, aucune ne
    dépend d'elle."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.qa"
    label = "qa"
    verbose_name = "Recette"
