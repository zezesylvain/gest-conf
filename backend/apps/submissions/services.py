"""Logique métier des soumissions (plan L3). Le statut ne change que par
``apps.submissions.workflow.transition`` (règle n° 4)."""

from __future__ import annotations

import re
from datetime import datetime

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.conferences.models import FilePolicy, KeyDateCode
from apps.conferences.services import is_call_open, key_date
from apps.submissions.declarations import missing_declarations
from apps.submissions.models import (
    Submission,
    SubmissionExtension,
    SubmissionFileKind,
)

KEYWORDS_MIN, KEYWORDS_MAX = 1, 6
_WORD = re.compile(r"\w+(?:['\u2019-]\w+)*")


def word_count(text: str) -> int:
    """Mots du résumé : suites de lettres ou chiffres, apostrophes et traits d'union
    internes compris (« l'appel », « bien-être » : un mot chacun)."""
    return len(_WORD.findall(text or ""))


def missing_items(submission: Submission) -> dict[str, list[str]]:
    """RG-01 : ce qui manque pour soumettre, par champ (vide : soumission complète).

    Champs obligatoires, au moins un auteur dont le soumissionnaire et au moins un
    correspondant, fichier selon le type (F1), déclarations dans leur version courante (F7).
    """
    edition = submission.edition
    problems: dict[str, list[str]] = {}

    def add(field: str, message) -> None:
        problems.setdefault(field, []).append(str(message))

    if not submission.title.strip():
        add("title", _("Titre obligatoire."))
    words = word_count(submission.abstract)
    submission_type = submission.submission_type
    if words == 0:
        add("abstract", _("Résumé obligatoire."))
    elif submission_type is not None and words > submission_type.abstract_max_words:
        add(
            "abstract",
            _("Résumé trop long : %(words)s mots pour %(max)s au plus.")
            % {"words": words, "max": submission_type.abstract_max_words},
        )
    keywords = [k for k in submission.keywords or [] if str(k).strip()]
    if not KEYWORDS_MIN <= len(keywords) <= KEYWORDS_MAX:
        add("keywords", _("De 1 à 6 mots-clés."))
    if submission.track is None or not submission.track.is_active:
        add("track", _("Choisissez une thématique active."))
    if submission_type is None or not submission_type.is_active:
        add("submission_type", _("Choisissez un type de communication actif."))
    if submission.language not in (edition.submission_languages or []):
        add("language", _("Choisissez une langue acceptée par l'édition."))

    authors = list(submission.authors.all())
    if not authors:
        add("authors", _("Au moins un auteur."))
    else:
        if not any(author.is_corresponding for author in authors):
            add("authors", _("Au moins un auteur correspondant."))
        if not any(author.user_id == submission.submitter_id for author in authors):
            add("authors", _("Le soumissionnaire fait partie des auteurs."))

    if submission_type is not None and submission_type.file_policy == FilePolicy.REQUIRED:
        has_file = submission.files.filter(kind=SubmissionFileKind.MAIN, is_current=True).exists()
        if not has_file:
            add("file", _("Fichier PDF obligatoire pour ce type de communication."))

    if missing_declarations(submission.declarations or {}):
        add("declarations", _("Acceptez toutes les déclarations."))
    return problems


def active_extension(submission: Submission, now: datetime | None = None):
    """Dérogation en cours (RG-02) : non révoquée, échéance non atteinte."""
    now = now or timezone.now()
    return (
        SubmissionExtension.objects.filter(
            submission=submission, revoked_at__isnull=True, until__gt=now
        )
        .order_by("-until")
        .first()
    )


def call_closed_at(submission: Submission) -> datetime | None:
    return key_date(submission.edition, KeyDateCode.CALL_CLOSE)


def can_write(submission: Submission, now: datetime | None = None) -> bool:
    """RG-02 : écriture de l'auteur permise si l'appel est ouvert, ou si une dérogation est
    en cours pour cette soumission."""
    now = now or timezone.now()
    return is_call_open(submission.edition, now) or active_extension(submission, now) is not None
