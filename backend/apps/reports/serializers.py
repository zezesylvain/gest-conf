"""Sérialiseurs des rapports (plan L8, N13) et du fil d'activité (N14)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers


class SectionSummarySerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class ReportTableSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    # Cellules : texte, entier ou décimal en chaîne (montants et taux exacts), ou nul.
    rows = serializers.ListField(
        child=serializers.ListField(child=serializers.CharField(allow_null=True))
    )


class ReportSectionSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    tables = ReportTableSerializer(many=True)


def _cell(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def tables_data(tables) -> list[dict[str, Any]]:
    """Cellules en chaînes : un décimal garde sa valeur exacte (jamais de flottant)."""
    return [
        {
            "key": table.key,
            "title": table.title,
            "columns": list(table.columns),
            "rows": [[_cell(value) for value in row] for row in table.rows],
        }
        for table in tables
    ]


class ActivityEntrySerializer(serializers.Serializer):
    at = serializers.DateTimeField()
    action = serializers.CharField()
    actor = serializers.CharField(allow_blank=True)
    object_type = serializers.CharField(allow_blank=True)
    object_id = serializers.CharField(allow_blank=True)
