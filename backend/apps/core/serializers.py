from django.db import models
from rest_framework import serializers

from apps.core.errors import ErrorCode


class HealthStatus(models.TextChoices):
    """État global renvoyé par /v1/health (nom de schéma ``HealthStatus``)."""

    OK = "ok"
    DEGRADED = "degraded"


class ServiceStatus(models.TextChoices):
    """État d'un service dépendant : base, cache (nom de schéma ``ServiceStatus``)."""

    OK = "ok"
    ERROR = "error"


class JobsStatus(models.TextChoices):
    """État de la file de tâches (nom de schéma ``JobsStatus``, plan L1 §8.4).

    ``late`` : le dernier passage réussi de ``run_jobs`` date de plus de trois
    intervalles du cron ; ``unknown`` : aucun passage réussi enregistré.
    """

    OK = "ok"
    LATE = "late"
    UNKNOWN = "unknown"


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=HealthStatus.choices)
    database = serializers.ChoiceField(choices=ServiceStatus.choices)
    # Cache partagé (table en base) : écriture, relecture puis suppression d'une clé.
    # Pas de help_text sur les champs à choix : il remplacerait la référence
    # « $ref » à l'énumération par un « allOf » dans le schéma.
    cache = serializers.ChoiceField(choices=ServiceStatus.choices)
    # Sans effet sur « status » : un cron arrêté n'empêche pas l'API de répondre.
    jobs = serializers.ChoiceField(choices=JobsStatus.choices)
    secure = serializers.BooleanField(
        help_text="Vrai si Django voit la requête comme HTTPS (contrôle du déploiement)."
    )
    release = serializers.CharField()


class ApiErrorSerializer(serializers.Serializer):
    """Format de toute réponse d'erreur de l'API : {code, message, fields}."""

    # Code stable, traduit par l'interface (énumération ErrorCode).
    code = serializers.ChoiceField(choices=ErrorCode.choices)
    message = serializers.CharField(help_text="Message lisible, dans la langue de la requête.")
    fields = serializers.DictField(
        child=serializers.JSONField(),
        help_text="Erreurs par champ : {nom du champ: [messages]} ; objet vide sinon.",
    )
