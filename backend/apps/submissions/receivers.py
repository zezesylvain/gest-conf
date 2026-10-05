"""Compteur des références créé avec l'édition, hors contention (voir
``apps.core.counters.ensure_counter``)."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.conferences.models import Edition


@receiver(post_save, sender=Edition, dispatch_uid="submissions_reference_counter")
def create_reference_counter(sender, instance: Edition, created: bool, raw: bool = False, **kw):
    if created and not raw:
        from apps.core.counters import ensure_counter
        from apps.submissions.models import reference_scope

        ensure_counter(reference_scope(instance))
