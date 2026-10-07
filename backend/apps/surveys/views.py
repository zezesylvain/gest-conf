"""Routes des questionnaires de satisfaction (plan L8, N12 ; RG-21).

- gestion ``v1/manage/editions/{id}/surveys`` (2FA) : ``surveys.manage`` (administrateur,
  Chair, CO « communication » et « secrétariat ») ; la publication, qui programme les
  invitations de toutes les personnes présentes, exige une réauthentification récente ;
  résultats agrégés à partir de 5 réponses ; export journalisé ;
- compte ``v1/me/surveys`` : ses invitations, le questionnaire et sa réponse (anonyme).
"""

from __future__ import annotations

from django.http import Http404, HttpResponse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import ManageViewSet, RecentAuthRequired
from apps.accounts.roles import Capability as C
from apps.core.actor import Actor
from apps.core.audit import record
from apps.core.errors import Invalid
from apps.core.spreadsheet import csv_response, csv_text, xlsx_bytes, xlsx_response
from apps.surveys import services
from apps.surveys.models import Survey, SurveyQuestion, SurveyStatus
from apps.surveys.serializers import (
    AnswerSerializer,
    MySurveyDetailSerializer,
    MySurveySerializer,
    QuestionSerializer,
    QuestionWriteSerializer,
    SurveyCreateSerializer,
    SurveyDetailSerializer,
    SurveyResultsSerializer,
    SurveySerializer,
    SurveyWriteSerializer,
    survey_data,
)


class SurveyViewSet(ManageViewSet):
    """``…/surveys`` : questionnaires, questions, publication, duplication, résultats."""

    pagination_class = None
    filter_backends = ()
    serializer_class = SurveySerializer
    required_capabilities = {
        name: C.SURVEYS_MANAGE
        for name in (
            "list",
            "create",
            "retrieve",
            "partial_update",
            "destroy",
            "publish",
            "duplicate",
            "add_question",
            "update_question",
            "delete_question",
            "results",
            "export",
        )
    }

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "publish":
            permissions.append(RecentAuthRequired())
        return permissions

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def survey(self, survey_id: int) -> Survey:
        survey = (
            Survey.objects.filter(pk=survey_id, edition=self.edition)
            .select_related("edition", "session")
            .first()
        )
        if survey is None:
            raise Http404
        return survey

    def question(self, survey: Survey, question_id: int) -> SurveyQuestion:
        question = survey.questions.filter(pk=question_id).select_related("survey__edition").first()
        if question is None:
            raise Http404
        return question

    def data(self, survey: Survey, *, questions: bool = True) -> dict:
        return survey_data(
            survey,
            is_open=services.is_open(survey),
            stats=services.stats(survey),
            questions=questions,
        )

    def detail_response(self, survey: Survey, code: int = 200) -> Response:
        survey = self.survey(survey.pk)
        return Response(SurveyDetailSerializer(self.data(survey)).data, status=code)

    @extend_schema(operation_id="manage_surveys_list", responses={200: SurveySerializer(many=True)})
    def list(self, request: Request, edition_id: int) -> Response:
        rows = Survey.objects.filter(edition=self.edition).select_related("edition", "session")
        return Response(
            SurveySerializer([self.data(row, questions=False) for row in rows], many=True).data
        )

    @extend_schema(
        operation_id="manage_surveys_create",
        request=SurveyCreateSerializer,
        responses={201: SurveyDetailSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = SurveyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        default_questions = data.pop("default_questions", True)
        survey = services.create_survey(
            self.edition, data, actor=self.actor(), default_questions=default_questions
        )
        return self.detail_response(survey, status.HTTP_201_CREATED)

    @extend_schema(operation_id="manage_surveys_retrieve", responses={200: SurveyDetailSerializer})
    def retrieve(self, request: Request, edition_id: int, survey_id: int) -> Response:
        return self.detail_response(self.survey(survey_id))

    @extend_schema(
        operation_id="manage_surveys_update",
        request=SurveyWriteSerializer,
        responses={200: SurveyDetailSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, survey_id: int) -> Response:
        serializer = SurveyWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        survey = services.update_survey(
            self.survey(survey_id), serializer.validated_data, actor=self.actor()
        )
        return self.detail_response(survey)

    @extend_schema(operation_id="manage_surveys_destroy", responses={204: None})
    def destroy(self, request: Request, edition_id: int, survey_id: int) -> Response:
        services.delete_survey(self.survey(survey_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="manage_surveys_publish", request=None, responses={200: SurveyDetailSerializer}
    )
    def publish(self, request: Request, edition_id: int, survey_id: int) -> Response:
        survey = services.publish(self.survey(survey_id), actor=self.actor())
        return self.detail_response(survey)

    @extend_schema(
        operation_id="manage_surveys_duplicate",
        request=None,
        responses={201: SurveyDetailSerializer},
    )
    def duplicate(self, request: Request, edition_id: int, survey_id: int) -> Response:
        copy = services.duplicate(self.survey(survey_id), actor=self.actor())
        return self.detail_response(copy, status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_surveys_questions_create",
        request=QuestionWriteSerializer,
        responses={201: QuestionSerializer},
    )
    def add_question(self, request: Request, edition_id: int, survey_id: int) -> Response:
        serializer = QuestionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        question = services.add_question(
            self.survey(survey_id), serializer.validated_data, actor=self.actor()
        )
        return Response(QuestionSerializer(question).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_surveys_questions_update",
        request=QuestionWriteSerializer,
        responses={200: QuestionSerializer},
    )
    def update_question(
        self, request: Request, edition_id: int, survey_id: int, question_id: int
    ) -> Response:
        serializer = QuestionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        survey = self.survey(survey_id)
        question = services.update_question(
            self.question(survey, question_id), serializer.validated_data, actor=self.actor()
        )
        return Response(QuestionSerializer(question).data)

    @extend_schema(operation_id="manage_surveys_questions_destroy", responses={204: None})
    def delete_question(
        self, request: Request, edition_id: int, survey_id: int, question_id: int
    ) -> Response:
        survey = self.survey(survey_id)
        services.delete_question(self.question(survey, question_id), actor=self.actor())
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(operation_id="manage_surveys_results", responses={200: SurveyResultsSerializer})
    def results(self, request: Request, edition_id: int, survey_id: int) -> Response:
        return Response(SurveyResultsSerializer(services.results(self.survey(survey_id))).data)

    @extend_schema(
        operation_id="manage_surveys_export",
        parameters=[OpenApiParameter("file_format", str, enum=["csv", "xlsx"])],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def export(self, request: Request, edition_id: int, survey_id: int) -> HttpResponse:
        """Agrégats et textes libres mélangés (N12), journalisé."""
        file_format = request.query_params.get("file_format", "csv")
        if file_format not in ("csv", "xlsx"):
            raise Invalid(fields={"file_format": [_("csv ou xlsx attendu.")]})
        survey = self.survey(survey_id)
        header, rows = services.export_rows(survey)
        record(
            "survey.exported",
            actor=self.actor(),
            edition=self.edition,
            obj=survey,
            after={"format": file_format, "rows": len(rows)},
        )
        name = (
            f"questionnaire-{self.edition.code}-{survey.pk}-{timezone.now():%Y%m%d}.{file_format}"
        )
        if file_format == "xlsx":
            return xlsx_response(xlsx_bytes(header, rows, title="Questionnaire"), name)
        return csv_response(csv_text(header, rows), name)


# --- Compte ------------------------------------------------------------------------------


def _my_data(invitation, *, detail: bool = False) -> dict:
    survey = invitation.survey
    data = {
        "id": survey.pk,
        "edition_id": survey.edition_id,
        "edition_code": survey.edition.code,
        "title_fr": survey.title_fr,
        "title_en": survey.title_en,
        "session_title": survey.session.title_fr if survey.session_id else "",
        "closes_at": survey.closes_at,
        "is_open": services.is_open(survey),
        "answered": invitation.answered_on is not None,
    }
    if detail:
        data.update(
            intro_fr=survey.intro_fr,
            intro_en=survey.intro_en,
            questions=list(survey.questions.all()),
        )
    return data


class MySurveysView(APIView):
    """``GET /v1/me/surveys`` : questionnaires auxquels la personne est invitée."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(operation_id="me_surveys", responses={200: MySurveySerializer(many=True)})
    def get(self, request: Request) -> Response:
        rows = services.my_invitations(request.user)
        return Response(MySurveySerializer([_my_data(row) for row in rows], many=True).data)


class MySurveyView(APIView):
    """``/v1/me/surveys/{id}`` : le questionnaire (invitée seulement, 404 sinon) et la
    réponse, enregistrée sans lien avec la personne (RG-21)."""

    permission_classes = (IsAuthenticated,)

    def invitation(self, request: Request, survey_id: int):
        survey = (
            Survey.objects.filter(pk=survey_id, status=SurveyStatus.PUBLISHED)
            .select_related("edition", "session")
            .first()
        )
        invitation = services.invitation_of(survey, request.user) if survey else None
        if invitation is None:
            raise Http404
        invitation.survey = survey
        return invitation

    @extend_schema(operation_id="me_survey_retrieve", responses={200: MySurveyDetailSerializer})
    def get(self, request: Request, survey_id: int) -> Response:
        invitation = self.invitation(request, survey_id)
        return Response(MySurveyDetailSerializer(_my_data(invitation, detail=True)).data)

    @extend_schema(
        operation_id="me_survey_answer",
        request=AnswerSerializer,
        responses={200: MySurveySerializer},
    )
    def post(self, request: Request, survey_id: int) -> Response:
        invitation = self.invitation(request, survey_id)
        serializer = AnswerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.answer(invitation.survey, request.user, serializer.validated_data["answers"])
        invitation.refresh_from_db()
        return Response(MySurveySerializer(_my_data(invitation)).data)
