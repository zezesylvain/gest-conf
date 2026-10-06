from django.apps import AppConfig


class ReviewsConfig(AppConfig):
    name = "apps.reviews"
    verbose_name = "Évaluation"

    def ready(self) -> None:
        from apps.core.integrity import register_integrity_check
        from apps.reviews import integrity
        from apps.reviews.notifications import register_review_templates
        from apps.reviews.personal_data import register_reviews_personal_data
        from apps.reviews.services import assignments
        from apps.submissions import workflow

        register_reviews_personal_data()
        register_review_templates()
        register_integrity_check("reviews.grid_weights", integrity.check_grid_weights)
        register_integrity_check("reviews.review_scores", integrity.check_review_scores)
        register_integrity_check("reviews.assignments", integrity.check_assignments)
        workflow.register_guard(assignments.guard_review_steps)
        workflow.register_effect(assignments.on_transition)
