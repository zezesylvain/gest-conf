"""Seed du portail à la création d'une édition (pages du site, sections « données », menu)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.conferences.models import Edition


@receiver(post_save, sender=Edition, dispatch_uid="portal_seed_new_edition")
def seed_new_edition(sender, instance: Edition, created: bool, raw: bool = False, **kwargs) -> None:
    # Ni fixture (``raw``), ni modification : seulement la création. Non audité à part :
    # l'entrée ``edition.created`` couvre la création et ce qu'elle livre.
    if created and not raw:
        from apps.portal.services import seed_portal

        seed_portal(instance)
