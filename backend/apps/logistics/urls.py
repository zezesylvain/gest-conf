"""Routes de l'organisation (plan L8 §4) : tâches (N3) et budget (N4)."""

from django.urls import path

from apps.logistics import views

app_name = "logistics"

E = "manage/editions/<int:edition_id>"
TASKS = views.TaskViewSet
T = f"{E}/tasks/<int:task_id>"
BUDGET = views.BudgetViewSet
L = f"{E}/budget/lines/<int:line_id>"

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
]
