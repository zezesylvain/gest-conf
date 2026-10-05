from django.db import models


class TimeStampedModel(models.Model):
    """Base de toutes les tables métier : horodatage de création et de mise à jour (étude §8.2)."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
