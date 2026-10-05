from rest_framework import serializers


class HealthSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok", "degraded"])
    database = serializers.ChoiceField(choices=["ok", "error"])
    secure = serializers.BooleanField(
        help_text="Vrai si Django voit la requête comme HTTPS (contrôle du déploiement)."
    )
    release = serializers.CharField()
