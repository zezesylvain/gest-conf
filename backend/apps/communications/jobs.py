"""Tâche d'envoi d'un e-mail du registre (plan L1 §8.3, « Gestionnaire d'envoi »)."""

from __future__ import annotations

import logging
from email.utils import parseaddr

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db.models import F
from django.utils import timezone

from apps.communications.models import OutboxEmail, OutboxStatus
from apps.communications.services import SEND_EMAIL_JOB, hourly_limit_reached
from apps.core.jobs import RetryLater, register_job
from apps.core.models import Job

logger = logging.getLogger(__name__)


def message_id(email: OutboxEmail) -> str:
    """``Message-ID`` dérivé de l'identifiant : un doublon d'envoi reste repérable."""
    domain = parseaddr(settings.DEFAULT_FROM_EMAIL)[1].rpartition("@")[2] or "localhost"
    return f"<gestconf.outbox.{email.pk}.{int(email.created_at.timestamp())}@{domain}>"


def build_message(email: OutboxEmail) -> EmailMultiAlternatives:
    message = EmailMultiAlternatives(
        subject=email.subject,
        body=email.body_text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email.to_email],
        headers={"Message-ID": message_id(email)},
        connection=get_connection(),
    )
    if email.body_html:
        message.attach_alternative(email.body_html, "text/html")
    return message


def _mark_failed(job: Job) -> None:
    OutboxEmail.objects.filter(pk=job.payload.get("outbox_id")).exclude(
        status=OutboxStatus.SENT
    ).update(status=OutboxStatus.FAILED)


@register_job(SEND_EMAIL_JOB, on_final_failure=_mark_failed)
def send_email(job: Job) -> None:
    """Envoie l'e-mail ``payload["outbox_id"]`` ; idempotent.

    1. Ignore un e-mail déjà envoyé ou annulé.
    2. Passe l'e-mail en ``sending`` ; la mise à jour est validée (mode
       autocommit) **avant** l'appel au fournisseur.
    3. Envoie, puis passe en ``sent`` et purge le corps s'il est sensible.

    Une panne entre l'acceptation par le fournisseur et l'étape 3 peut produire
    un doublon : rare, assumé pour des e-mails transactionnels (plan §8.3).
    """
    email = OutboxEmail.objects.filter(pk=job.payload["outbox_id"]).first()
    if email is None or email.status in (OutboxStatus.SENT, OutboxStatus.CANCELLED):
        return
    if email.purged_at is not None:
        # Corps sensible purgé avant tout envoi (cron arrêté plus de 24 h) : rien à envoyer.
        OutboxEmail.objects.filter(pk=email.pk).update(status=OutboxStatus.FAILED)
        return
    now = timezone.now()
    retry_at = hourly_limit_reached(now, bulk=email.is_bulk)
    if retry_at is not None:
        raise RetryLater(retry_at)

    OutboxEmail.objects.filter(pk=email.pk).update(
        status=OutboxStatus.SENDING, attempts=F("attempts") + 1
    )
    message = build_message(email)
    try:
        message.send(fail_silently=False)
    except Exception as exc:
        OutboxEmail.objects.filter(pk=email.pk, status=OutboxStatus.SENDING).update(
            status=OutboxStatus.QUEUED,
            last_error=f"{type(exc).__module__}.{type(exc).__qualname__}",
        )
        raise

    status = getattr(message, "anymail_status", None)
    provider_id = getattr(status, "message_id", None) if status is not None else None
    sent_at = timezone.now()
    update = {
        "status": OutboxStatus.SENT,
        "sent_at": sent_at,
        "last_error": "",
        "provider_message_id": str(provider_id)[:255] if provider_id else "",
    }
    if email.is_sensitive:
        update.update(body_text="", body_html="", purged_at=sent_at)
    OutboxEmail.objects.filter(pk=email.pk).update(**update)


@register_job("communications.fan_out")
def fan_out(job: Job) -> None:
    """Un lot de la mise en file d'une annonce (plan L8, N11) ; le lot suivant est remis en
    file par le service tant qu'il reste des destinataires. Idempotent."""
    from apps.communications.announcements import fan_out_batch

    fan_out_batch(int(job.payload["announcement_id"]))
