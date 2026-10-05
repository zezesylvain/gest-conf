"""Logique métier des soumissions (plan L3). Le statut ne change que par
``apps.submissions.workflow.transition`` (règle n° 4)."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.conferences.models import Edition, EditionStatus, FilePolicy, KeyDateCode
from apps.conferences.services import is_call_open, key_date
from apps.core.actor import Actor, ActorKind
from apps.core.audit import record
from apps.core.errors import ErrorCode, Invalid, NotAllowed, RuleViolation, StaleRevision
from apps.submissions.declarations import DECLARATIONS, missing_declarations
from apps.submissions.models import (
    Submission,
    SubmissionAuthor,
    SubmissionExtension,
    SubmissionFile,
    SubmissionFileKind,
    SubmissionRevision,
    SubmissionStatus,
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


# --- Écritures de l'auteur (plan L3 §4) ---------------------------------------------------

EDITABLE_STATUSES = (SubmissionStatus.DRAFT, SubmissionStatus.SUBMITTED)
MAX_AUTHORS = 30
KEYWORD_MAX_LENGTH = 60
ABSTRACT_MAX_CHARS = 30_000


def _lock(submission: Submission) -> Submission:
    return (
        Submission.objects.select_for_update()
        .select_related("edition", "track", "submission_type", "submitter")
        .get(pk=submission.pk)
    )


def _check_writable(
    submission: Submission, actor: Actor, expected_revision: int | None, now: datetime
) -> None:
    """Auteur seul ; état modifiable ; RG-02 (appel ouvert ou dérogation) ; If-Match."""
    if actor.kind != ActorKind.USER or actor.user is None:
        raise NotAllowed()
    if actor.user.pk != submission.submitter_id:
        raise NotAllowed()
    if submission.edition.status == EditionStatus.ARCHIVED:
        raise RuleViolation(code=ErrorCode.EDITION_ARCHIVED)
    if submission.status not in EDITABLE_STATUSES:
        raise RuleViolation(
            _("Cette soumission n'est plus modifiable."), code=ErrorCode.SUBMISSION_LOCKED
        )
    if not can_write(submission, now):
        raise RuleViolation(_("L'appel à communications est clos."), code=ErrorCode.CALL_CLOSED)
    if expected_revision is not None and expected_revision != submission.revision:
        raise StaleRevision()


def snapshot(submission: Submission) -> dict[str, Any]:
    """Cliché d'une révision (F3) : métadonnées, auteurs, fichier courant."""
    current = submission.files.filter(kind=SubmissionFileKind.MAIN, is_current=True).first()
    return {
        "title": submission.title,
        "abstract": submission.abstract,
        "keywords": list(submission.keywords or []),
        "language": submission.language,
        "track": submission.track_id,
        "submission_type": submission.submission_type_id,
        "authors": [
            {
                "position": author.position,
                "first_name": author.first_name,
                "last_name": author.last_name,
                "email": author.email,
                "institution": author.institution,
                "country": author.country,
                "is_corresponding": author.is_corresponding,
                "is_presenter": author.is_presenter,
            }
            for author in submission.authors.all()
        ],
        "file": (
            {"version": current.version, "sha256": current.sha256, "name": current.original_name}
            if current
            else None
        ),
    }


def _written(submission: Submission, actor: Actor, now: datetime, fields: list[str]) -> None:
    """Après une écriture : révision suivante ; cliché si la soumission est déjà soumise."""
    submission.revision += 1
    submission.save(update_fields=[*fields, "revision", "updated_at"])
    if submission.status == SubmissionStatus.SUBMITTED:
        number = (
            SubmissionRevision.objects.filter(submission=submission).aggregate(Max("number"))[
                "number__max"
            ]
            or 0
        ) + 1
        SubmissionRevision.objects.create(
            submission=submission,
            number=number,
            at=now,
            actor=actor.user,
            snapshot=snapshot(submission),
        )


@transaction.atomic
def create_draft(edition: Edition, *, actor: Actor) -> Submission:
    """Brouillon (appel ouvert, profil complet). Rôle ``AUTHOR`` attribué au premier
    brouillon de l'édition (D7) ; le soumissionnaire est le premier auteur (F6)."""
    from apps.accounts.models import RoleSource
    from apps.accounts.roles import Role
    from apps.accounts.services.account import get_profile
    from apps.accounts.services.roles import grant_role

    user = actor.user
    if actor.kind != ActorKind.USER or user is None:
        raise NotAllowed()
    profile = get_profile(user)
    if profile._state.adding or not profile.is_complete:
        raise RuleViolation(
            _("Complétez votre profil (nom, prénom, institution, pays) avant de soumettre."),
            code=ErrorCode.PROFILE_INCOMPLETE,
        )
    if not is_call_open(edition):
        raise RuleViolation(_("L'appel à communications est clos."), code=ErrorCode.CALL_CLOSED)
    submission = Submission.objects.create(edition=edition, submitter=user)
    SubmissionAuthor.objects.create(
        submission=submission,
        position=1,
        user=user,
        first_name=profile.first_name,
        last_name=profile.last_name,
        email=user.email,
        institution=profile.institution,
        country=profile.country,
        is_corresponding=True,
        is_presenter=True,
    )
    grant_role(
        user=user,
        edition=edition,
        role=Role.AUTHOR,
        actor=Actor.system("submission:draft"),
        source=RoleSource.SYSTEM,
    )
    record("submission.created", actor=actor, edition=edition, obj=submission)
    return submission


def _clean_keywords(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise Invalid(fields={"keywords": [_("Liste attendue.")]})
    keywords: list[str] = []
    for item in value:
        text = " ".join(str(item).split())
        if not text:
            continue
        if len(text) > KEYWORD_MAX_LENGTH:
            raise Invalid(
                fields={
                    "keywords": [_("%(max)s caractères au plus.") % {"max": KEYWORD_MAX_LENGTH}]
                }
            )
        if text.lower() not in {k.lower() for k in keywords}:
            keywords.append(text)
    if len(keywords) > KEYWORDS_MAX:
        raise Invalid(fields={"keywords": [_("De 1 à 6 mots-clés.")]})
    return keywords


@transaction.atomic
def update_submission(
    submission: Submission,
    data: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    now: datetime | None = None,
) -> Submission:
    """Métadonnées et déclarations. Les valeurs incomplètes sont admises en brouillon
    (sauvegarde automatique) ; la complétude se contrôle à la soumission (RG-01)."""
    now = now or timezone.now()
    submission = _lock(submission)
    _check_writable(submission, actor, expected_revision, now)
    edition = submission.edition
    changed: list[str] = []
    if "title" in data:
        submission.title = " ".join(str(data["title"]).split())[:300]
        changed.append("title")
    if "abstract" in data:
        abstract = str(data["abstract"]).strip()
        if len(abstract) > ABSTRACT_MAX_CHARS:
            raise Invalid(fields={"abstract": [_("Résumé trop long.")]})
        submission.abstract = abstract
        changed.append("abstract")
    if "keywords" in data:
        submission.keywords = _clean_keywords(data["keywords"])
        changed.append("keywords")
    if "language" in data:
        language = data["language"] or ""
        if language and language not in (edition.submission_languages or []):
            raise Invalid(fields={"language": [_("Langue non acceptée par l'édition.")]})
        submission.language = language
        changed.append("language")
    for name in ("track", "submission_type"):
        if name in data:
            value = data[name]
            if value is not None and (value.edition_id != edition.pk or not value.is_active):
                raise Invalid(fields={name: [_("Choix invalide pour cette édition.")]})
            setattr(submission, name, value)
            changed.append(name)
    if "declarations" in data:
        declarations = data["declarations"] or {}
        unknown = set(declarations) - set(DECLARATIONS)
        if unknown:
            raise Invalid(fields={"declarations": [_("Déclaration inconnue.")]})
        stored = dict(submission.declarations or {})
        for code, accepted in declarations.items():
            stored[code] = {"accepted": bool(accepted), "text_version": DECLARATIONS[code]}
        submission.declarations = stored
        changed.append("declarations")
    changed = list(dict.fromkeys(changed))
    if not changed:
        return submission
    _written(submission, actor, now, changed)
    record(
        "submission.updated",
        actor=actor,
        edition=edition,
        obj=submission,
        after={"fields": changed},
    )
    return submission


def _verified_user(email: str):
    from allauth.account.models import EmailAddress

    address = (
        EmailAddress.objects.filter(email__iexact=email, verified=True)
        .select_related("user")
        .first()
    )
    return address.user if address and address.user.is_active else None


@transaction.atomic
def set_authors(
    submission: Submission,
    authors: Sequence[Mapping[str, Any]],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    now: datetime | None = None,
) -> Submission:
    """Liste **complète** et ordonnée des auteurs (F5). Un auteur est rattaché au compte
    dont l'adresse vérifiée correspond. Correspondant et présence du soumissionnaire :
    contrôlés à la soumission (RG-01)."""
    from apps.accounts.validators import validate_country

    now = now or timezone.now()
    submission = _lock(submission)
    _check_writable(submission, actor, expected_revision, now)
    if not 1 <= len(authors) <= MAX_AUTHORS:
        raise Invalid(fields={"authors": [_("De 1 à 30 auteurs.")]})
    seen: set[str] = set()
    rows = []
    for position, item in enumerate(authors, start=1):
        email = str(item.get("email", "")).strip().lower()
        first_name = " ".join(str(item.get("first_name", "")).split())
        last_name = " ".join(str(item.get("last_name", "")).split())
        country = str(item.get("country", "") or "").upper()
        errors: dict[str, list] = {}
        if not first_name or not last_name:
            errors["name"] = [_("Nom et prénom obligatoires.")]
        if not email or "@" not in email:
            errors["email"] = [_("Adresse e-mail obligatoire.")]
        elif email in seen:
            errors["email"] = [_("Adresse en double.")]
        if country:
            try:
                validate_country(country)
            except ValidationError:
                errors["country"] = [_("Pays inconnu.")]
        if errors:
            raise Invalid(
                fields={f"authors.{position}.{key}": value for key, value in errors.items()}
            )
        seen.add(email)
        rows.append(
            SubmissionAuthor(
                submission=submission,
                position=position,
                user=_verified_user(email),
                first_name=first_name[:150],
                last_name=last_name[:150],
                email=email,
                institution=" ".join(str(item.get("institution", "")).split())[:255],
                country=country,
                is_corresponding=bool(item.get("is_corresponding")),
                is_presenter=bool(item.get("is_presenter")),
            )
        )
    submission.authors.all().delete()
    SubmissionAuthor.objects.bulk_create(rows)
    _written(submission, actor, now, [])
    record(
        "submission.authors_updated",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        after={"count": len(rows)},
    )
    return submission


@transaction.atomic
def upload_file(
    submission: Submission,
    *,
    data: bytes,
    name: str,
    actor: Actor,
    expected_revision: int | None = None,
    now: datetime | None = None,
) -> SubmissionFile:
    """Dépôt du PDF principal, nouvelle version (F2, F3). En double aveugle, le fichier
    stocké est la version nettoyée de ses métadonnées ; l'original n'est pas conservé."""
    from apps.submissions import pdf, storage

    now = now or timezone.now()
    submission = _lock(submission)
    _check_writable(submission, actor, expected_revision, now)
    submission_type = submission.submission_type
    if submission_type is None:
        raise Invalid(fields={"file": [_("Choisissez d'abord le type de communication.")]})
    if submission_type.file_policy == FilePolicy.NONE:
        raise Invalid(fields={"file": [_("Ce type de communication ne prend pas de fichier.")]})
    if not name.lower().endswith(".pdf"):
        raise Invalid(fields={"file": [_("Fichier PDF attendu (.pdf).")]})
    limit = submission_type.max_file_mb * 1024 * 1024
    if len(data) > limit:
        raise Invalid(
            fields={
                "file": [
                    _("Fichier trop volumineux (%(max)s Mo au plus).")
                    % {"max": submission_type.max_file_mb}
                ]
            }
        )
    checked = pdf.check_pdf(data, anonymize=submission.edition.double_blind)
    storage_name, digest = storage.write(checked.data)
    previous = SubmissionFile.objects.filter(
        submission=submission, kind=SubmissionFileKind.MAIN
    ).aggregate(Max("version"))["version__max"]
    SubmissionFile.objects.filter(
        submission=submission, kind=SubmissionFileKind.MAIN, is_current=True
    ).update(is_current=False, updated_at=now)
    stored = SubmissionFile.objects.create(
        submission=submission,
        kind=SubmissionFileKind.MAIN,
        version=(previous or 0) + 1,
        storage_name=storage_name,
        original_name=_safe_name(name),
        size=len(checked.data),
        sha256=digest,
        pages=checked.pages,
        metadata_removed=checked.metadata_removed,
        uploaded_by=actor.user,
    )
    _written(submission, actor, now, [])
    record(
        "submission.file_uploaded",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        after={
            "version": stored.version,
            "pages": stored.pages,
            "metadata_removed": stored.metadata_removed,
        },
    )
    return stored


def _safe_name(name: str) -> str:
    """Nom d'origine affiché (jamais utilisé pour le stockage) : sans chemin ni contrôle."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(char for char in base if char.isprintable()).strip()
    return cleaned[-255:] or "document.pdf"


@transaction.atomic
def remove_file(
    submission: Submission,
    *,
    actor: Actor,
    expected_revision: int | None = None,
    now: datetime | None = None,
) -> Submission:
    """Retire le fichier courant (les versions restent conservées, F3)."""
    now = now or timezone.now()
    submission = _lock(submission)
    _check_writable(submission, actor, expected_revision, now)
    updated = SubmissionFile.objects.filter(
        submission=submission, kind=SubmissionFileKind.MAIN, is_current=True
    ).update(is_current=False, updated_at=now)
    if updated:
        _written(submission, actor, now, [])
        record("submission.file_removed", actor=actor, edition=submission.edition, obj=submission)
    return submission


@transaction.atomic
def delete_draft(submission: Submission, *, actor: Actor) -> None:
    """Suppression d'un brouillon (et de ses fichiers) ; une soumission se retire."""
    from apps.submissions import storage

    submission = _lock(submission)
    if actor.kind != ActorKind.USER or actor.user is None:
        raise NotAllowed()
    if actor.user.pk != submission.submitter_id:
        raise NotAllowed()
    if submission.status != SubmissionStatus.DRAFT:
        raise RuleViolation(
            _("Une soumission envoyée ne se supprime pas : retirez-la."),
            code=ErrorCode.SUBMISSION_LOCKED,
        )
    record(
        "submission.draft_deleted",
        actor=actor,
        edition=submission.edition,
        after={"submission": submission.pk},
    )
    storage.delete_all(submission)
    submission.authors.all().delete()
    submission.delete()


# --- Dérogations (RG-02, F8) ----------------------------------------------------------------


@transaction.atomic
def grant_extension(
    submission: Submission, *, until_local: datetime, reason: str, actor: Actor
) -> SubmissionExtension:
    """Dérogation jusqu'à ``until_local`` (heure de l'édition, D13), avec motif. Droit
    ``submissions.extend`` vérifié par la vue (règle n° 2)."""
    from apps.conferences.services import local_to_utc
    from apps.submissions.notifications import extension_granted

    submission = _lock(submission)
    if submission.edition.status == EditionStatus.ARCHIVED:
        raise RuleViolation(code=ErrorCode.EDITION_ARCHIVED)
    if submission.status not in EDITABLE_STATUSES:
        raise RuleViolation(
            _("Dérogation impossible : la soumission n'est plus modifiable."),
            code=ErrorCode.SUBMISSION_LOCKED,
        )
    if not reason.strip():
        raise Invalid(fields={"reason": [_("Motif obligatoire.")]})
    try:
        until = local_to_utc(until_local, submission.edition.timezone)
    except Invalid as error:
        raise Invalid(fields={"until_local": error.fields.get("at_local", [])}) from error
    if until <= timezone.now():
        raise Invalid(fields={"until_local": [_("Échéance dans le futur attendue.")]})
    extension = SubmissionExtension.objects.create(
        submission=submission,
        until=until,
        reason=reason.strip(),
        granted_by=actor.user if actor.kind == ActorKind.USER else None,
        granted_at=timezone.now(),
    )
    record(
        "submission.extension_granted",
        actor=actor,
        edition=submission.edition,
        obj=submission,
        after={"until": until},
        reason=reason.strip(),
    )
    extension_granted(extension)
    return extension


@transaction.atomic
def revoke_extension(extension: SubmissionExtension, *, actor: Actor) -> SubmissionExtension:
    extension = SubmissionExtension.objects.select_for_update().get(pk=extension.pk)
    if extension.revoked_at is None:
        extension.revoked_at = timezone.now()
        extension.save(update_fields=["revoked_at", "updated_at"])
        record(
            "submission.extension_revoked",
            actor=actor,
            edition=extension.submission.edition,
            obj=extension.submission,
        )
    return extension
