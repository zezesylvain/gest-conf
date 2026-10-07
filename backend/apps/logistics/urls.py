"""Routes de l'organisation (plan L8 §4) : tâches (N3) et budget (N4)."""

from django.urls import path

from apps.logistics import views

app_name = "logistics"

E = "manage/editions/<int:edition_id>"
TASKS = views.TaskViewSet
T = f"{E}/tasks/<int:task_id>"
BUDGET = views.BudgetViewSet
L = f"{E}/budget/lines/<int:line_id>"
LOG = f"{E}/logistics"
VISITS = views.VisitViewSet
MEALS = views.MealViewSet
SHIFTS = views.ShiftViewSet

urlpatterns = [
    path(f"{E}/tasks", TASKS.as_view({"get": "list", "post": "create"}), name="manage-tasks"),
    path(f"{E}/tasks/members", TASKS.as_view({"get": "members"}), name="manage-tasks-members"),
    path(T, TASKS.as_view({"get": "retrieve", "patch": "partial_update"}), name="manage-task"),
    path(f"{T}/archive", TASKS.as_view({"post": "archive"}), name="manage-task-archive"),
    path(f"{T}/restore", TASKS.as_view({"post": "restore"}), name="manage-task-restore"),
    path(f"{T}/comments", TASKS.as_view({"post": "comment"}), name="manage-task-comments"),
    path(
        f"{T}/attachments",
        views.TaskAttachmentUploadViewSet.as_view({"post": "upload"}),
        name="manage-task-attachments",
    ),
    path(
        f"{T}/attachments/<int:attachment_id>",
        TASKS.as_view({"get": "attachment", "delete": "remove_attachment"}),
        name="manage-task-attachment",
    ),
    path(f"{E}/budget", BUDGET.as_view({"get": "retrieve"}), name="manage-budget"),
    path(f"{E}/budget/export", BUDGET.as_view({"get": "export"}), name="manage-budget-export"),
    path(f"{E}/budget/lines", BUDGET.as_view({"post": "create"}), name="manage-budget-lines"),
    path(
        L,
        BUDGET.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-budget-line",
    ),
    path(
        f"{L}/proof",
        views.BudgetProofViewSet.as_view(
            {"get": "proof", "put": "upload_proof", "delete": "remove_proof"}
        ),
        name="manage-budget-line-proof",
    ),
    path(f"{LOG}/visits", VISITS.as_view({"get": "list"}), name="manage-visits"),
    path(
        f"{LOG}/visits/<int:user_id>",
        VISITS.as_view({"get": "retrieve", "patch": "partial_update"}),
        name="manage-visit",
    ),
    path(
        f"{LOG}/dietary",
        views.DietaryViewSet.as_view({"get": "retrieve"}),
        name="manage-dietary",
    ),
    path(
        f"{LOG}/dietary/export",
        views.DietaryViewSet.as_view({"get": "export"}),
        name="manage-dietary-export",
    ),
    path(f"{LOG}/meals", MEALS.as_view({"get": "list", "post": "create"}), name="manage-meals"),
    path(f"{LOG}/meals/export", MEALS.as_view({"get": "export"}), name="manage-meals-export"),
    path(
        f"{LOG}/meals/<int:meal_id>",
        MEALS.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-meal",
    ),
    path(f"{LOG}/shifts", SHIFTS.as_view({"get": "list", "post": "create"}), name="manage-shifts"),
    path(
        f"{LOG}/shifts/<int:shift_id>",
        SHIFTS.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="manage-shift",
    ),
    path(
        f"{LOG}/shifts/<int:shift_id>/assignments",
        SHIFTS.as_view({"post": "assign"}),
        name="manage-shift-assignments",
    ),
    path(
        f"{LOG}/shifts/<int:shift_id>/assignments/<int:volunteer_id>",
        SHIFTS.as_view({"delete": "unassign"}),
        name="manage-shift-assignment",
    ),
    path(
        f"{E}/me/shifts",
        views.MyShiftsViewSet.as_view({"get": "list"}),
        name="manage-my-shifts",
    ),
    path(
        f"{E}/me/shifts/calendar",
        views.MyShiftsViewSet.as_view({"get": "calendar"}),
        name="manage-my-shifts-calendar",
    ),
    path("me/editions/<int:edition_id>/visit", views.MyVisitView.as_view(), name="me-visit"),
    path("me/editions/<int:edition_id>/dietary", views.MyDietaryView.as_view(), name="me-dietary"),
]
