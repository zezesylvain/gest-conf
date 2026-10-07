from django.apps import AppConfig


class SurveysConfig(AppConfig):
    name = "apps.surveys"
    verbose_name = "Questionnaires de satisfaction"

    def ready(self) -> None:
        from apps.communications.services import register_email_template
        from apps.core.integrity import register_integrity_check
        from apps.core.personal_data import register_personal_data
        from apps.surveys import jobs  # noqa: F401  (enregistre les tâches datées)
        from apps.surveys.integrity import check_responses
        from apps.surveys.personal_data import anonymize_surveys, export_surveys
        from apps.surveys.services import INVITATION_TEMPLATE, REMINDER_TEMPLATE

        register_email_template(INVITATION_TEMPLATE)
        register_email_template(REMINDER_TEMPLATE)
        register_integrity_check("surveys.responses", check_responses)
        # Les réponses ne sont liées à personne (RG-21) : seules les invitations et la mention
        # « créé par » d'un questionnaire sont des données personnelles.
        register_personal_data(
            "surveys.invitations",
            models=("surveys.Survey", "surveys.SurveyInvitation"),
            export=export_surveys,
            anonymize=anonymize_surveys,
        )
