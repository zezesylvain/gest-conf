"""Données fictives (plan L9, S6 et S10) : repérage et garde-fous.

Les données fictives vivent dans une conférence dédiée (``FICTITIOUS_CONFERENCE``) et des
comptes en ``@fictif.invalid`` (domaine réservé, RFC 2606) : aucun e-mail ne part vers eux
(la tâche d'envoi les annule). Les commandes qui en créent sont refusées dès que la base
contient des données réelles : un compte hors du domaine fictif, une soumission ou une
inscription hors de la conférence fictive. Pour revenir à l'état antérieur, on restaure la
sauvegarde prise juste avant (``backup_db``, puis ``restore_db`` dans une base neuve) : pas
de commande de purge, qui supprimerait des pièces comptables numérotées en ajout seul
(RG-14) et le journal, et se heurterait aux clés ``RESTRICT``.
"""

from __future__ import annotations

from django.core.management.base import CommandError

FICTITIOUS_CONFERENCE = "gestconf-fictif"
FICTITIOUS_DOMAIN = "fictif.invalid"
CONFIRM_OPTION = "--confirm-fictitious"


def fictitious_email(local_part: str) -> str:
    return f"{local_part}@{FICTITIOUS_DOMAIN}"


def is_fictitious_email(address: str) -> bool:
    return address.lower().endswith("@" + FICTITIOUS_DOMAIN)


def real_data_counts() -> dict[str, int]:
    """Données réelles : comptes hors du domaine fictif, soumissions et inscriptions hors de
    la conférence fictive. Les opérateurs n'ont pas besoin de compte pour lancer les
    commandes (D1) : sur une base neuve, tout compte est celui d'une personne réelle."""
    from apps.accounts.models import User
    from apps.registrations.models import Registration
    from apps.submissions.models import Submission

    return {
        "comptes": User.objects.exclude(email__iendswith="@" + FICTITIOUS_DOMAIN).count(),
        "soumissions": Submission.objects.exclude(
            edition__conference__slug=FICTITIOUS_CONFERENCE
        ).count(),
        "inscriptions": Registration.objects.exclude(
            edition__conference__slug=FICTITIOUS_CONFERENCE
        ).count(),
    }


def ensure_fictitious_only(*, confirmed: bool) -> None:
    """Refus sans confirmation explicite, ou dès qu'une donnée réelle existe."""
    if not confirmed:
        raise CommandError(
            f"Données fictives : relancer avec {CONFIRM_OPTION} (base sans donnée réelle, "
            "sauvegarde prise juste avant ; voir docs/L9-runbook-o2switch.md)."
        )
    real = {name: count for name, count in real_data_counts().items() if count}
    if real:
        details = ", ".join(f"{count} {name}" for name, count in real.items())
        raise CommandError(f"La base contient des données réelles ({details}) : refusé.")
