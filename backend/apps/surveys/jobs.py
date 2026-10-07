"""Tâches datées des questionnaires (plan L8, N12 et N17) : invitations à l'ouverture,
relance unique à mi-parcours ; chacune par lots, remise en file tant qu'il en reste."""

from __future__ import annotations

from apps.core.jobs import register_job
from apps.core.models import Job
from apps.surveys.services import INVITE_JOB, REMIND_JOB, invite_batch, remind_batch


@register_job(INVITE_JOB)
def invite(job: Job) -> None:
    invite_batch(int(job.payload["survey_id"]))


@register_job(REMIND_JOB)
def remind(job: Job) -> None:
    remind_batch(int(job.payload["survey_id"]))
