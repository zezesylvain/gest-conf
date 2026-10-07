"""Routes des questionnaires de satisfaction (plan L8, N12)."""

from django.urls import path

from apps.surveys import views

app_name = "surveys"

E = "manage/editions/<int:edition_id>"
SURVEYS = views.SurveyViewSet
S = f"{E}/surveys/<int:survey_id>"

urlpatterns = [
    path(f"{E}/surveys", SURVEYS.as_view({"get": "list", "post": "create"}), name="manage-surveys"),
    path(
        S,
        SURVEYS.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="manage-survey",
    ),
    path(f"{S}/publish", SURVEYS.as_view({"post": "publish"}), name="manage-survey-publish"),
    path(f"{S}/duplicate", SURVEYS.as_view({"post": "duplicate"}), name="manage-survey-duplicate"),
    path(
        f"{S}/questions",
        SURVEYS.as_view({"post": "add_question"}),
        name="manage-survey-questions",
    ),
    path(
        f"{S}/questions/<int:question_id>",
        SURVEYS.as_view({"patch": "update_question", "delete": "delete_question"}),
        name="manage-survey-question",
    ),
    path(f"{S}/results", SURVEYS.as_view({"get": "results"}), name="manage-survey-results"),
    path(f"{S}/export", SURVEYS.as_view({"get": "export"}), name="manage-survey-export"),
    path("me/surveys", views.MySurveysView.as_view(), name="me-surveys"),
    path("me/surveys/<int:survey_id>", views.MySurveyView.as_view(), name="me-survey"),
]
