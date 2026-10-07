"""Sérialiseurs des questionnaires (plan L8, N12). Aucun ne relie une réponse à une
personne (RG-21) : la gestion ne lit que des agrégats, la personne ne lit que ses
invitations."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.conferences.serializers import LocalDateTimeField
from apps.conferences.services import utc_to_local
from apps.surveys.models import QuestionKind, Survey, SurveyScope, SurveyStatus


def _local(value, edition) -> str | None:
    if value is None:
        return None
    return utc_to_local(value, edition.timezone).strftime("%Y-%m-%dT%H:%M")


class ChoiceSerializer(serializers.Serializer):
    value = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField(allow_blank=True)


class QuestionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    position = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=QuestionKind.choices)
    label_fr = serializers.CharField()
    label_en = serializers.CharField(allow_blank=True)
    choices = ChoiceSerializer(many=True)
    required = serializers.BooleanField()


class QuestionWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=QuestionKind.choices, required=False)
    label_fr = serializers.CharField(max_length=300, required=False)
    label_en = serializers.CharField(max_length=300, required=False, allow_blank=True)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    required = serializers.BooleanField(required=False)
    position = serializers.IntegerField(min_value=0, required=False)


class SurveyStatsSerializer(serializers.Serializer):
    invited = serializers.IntegerField()
    answered = serializers.IntegerField()
    responses = serializers.IntegerField()
    threshold = serializers.IntegerField()


class SurveySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    scope = serializers.ChoiceField(choices=SurveyScope.choices)
    session = serializers.IntegerField(allow_null=True)
    session_title = serializers.CharField(allow_blank=True)
    title_fr = serializers.CharField()
    title_en = serializers.CharField(allow_blank=True)
    intro_fr = serializers.CharField(allow_blank=True)
    intro_en = serializers.CharField(allow_blank=True)
    opens_local = serializers.CharField(allow_null=True)
    closes_local = serializers.CharField(allow_null=True)
    status = serializers.ChoiceField(choices=SurveyStatus.choices)
    is_open = serializers.BooleanField()
    locked = serializers.BooleanField()
    stats = SurveyStatsSerializer()


class SurveyDetailSerializer(SurveySerializer):
    questions = QuestionSerializer(many=True)


def survey_data(
    survey: Survey, *, is_open: bool, stats: dict, questions: bool = False
) -> dict[str, Any]:
    edition = survey.edition
    data: dict[str, Any] = {
        "id": survey.pk,
        "scope": survey.scope,
        "session": survey.session_id,
        "session_title": survey.session.title_fr if survey.session_id else "",
        "title_fr": survey.title_fr,
        "title_en": survey.title_en,
        "intro_fr": survey.intro_fr,
        "intro_en": survey.intro_en,
        "opens_local": _local(survey.opens_at, edition),
        "closes_local": _local(survey.closes_at, edition),
        "status": survey.status,
        "is_open": is_open,
        "locked": survey.locked_at is not None,
        "stats": stats,
    }
    if questions:
        data["questions"] = list(survey.questions.all())
    return data


class SurveyWriteSerializer(serializers.Serializer):
    scope = serializers.ChoiceField(choices=SurveyScope.choices, required=False)
    session = serializers.IntegerField(required=False, allow_null=True)
    title_fr = serializers.CharField(max_length=150, required=False)
    title_en = serializers.CharField(max_length=150, required=False, allow_blank=True)
    intro_fr = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    intro_en = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    opens_local = LocalDateTimeField(required=False, allow_null=True)
    closes_local = LocalDateTimeField(required=False, allow_null=True)


class SurveyCreateSerializer(SurveyWriteSerializer):
    default_questions = serializers.BooleanField(required=False, default=True)


class CountSerializer(serializers.Serializer):
    value = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField(allow_blank=True)
    count = serializers.IntegerField()


class QuestionResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=QuestionKind.choices)
    label_fr = serializers.CharField()
    label_en = serializers.CharField(allow_blank=True)
    answers = serializers.IntegerField()
    average = serializers.DecimalField(max_digits=4, decimal_places=2, allow_null=True)
    counts = CountSerializer(many=True)


class SurveyResultsSerializer(SurveyStatsSerializer):
    questions = QuestionResultSerializer(many=True)


class MySurveySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    edition_id = serializers.IntegerField()
    edition_code = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField(allow_blank=True)
    session_title = serializers.CharField(allow_blank=True)
    closes_at = serializers.DateTimeField()
    is_open = serializers.BooleanField()
    answered = serializers.BooleanField()


class MySurveyDetailSerializer(MySurveySerializer):
    intro_fr = serializers.CharField(allow_blank=True)
    intro_en = serializers.CharField(allow_blank=True)
    questions = QuestionSerializer(many=True)


class AnswerSerializer(serializers.Serializer):
    answers = serializers.DictField()
