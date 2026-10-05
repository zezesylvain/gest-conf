"""Contrôles d'intégrité des soumissions (``check_integrity``, plan L3 §3). Lecture seule ;
anomalies sans donnée personnelle (identifiants et références seulement)."""

from __future__ import annotations

from django.db.models import Count

from apps.core.models import Counter
from apps.submissions import storage
from apps.submissions.models import Submission, SubmissionFile, reference_scope


def check_current_files() -> list[str]:
    """Au plus un fichier courant par (soumission, nature) : garanti par le service, pas
    par une contrainte (MariaDB n'a pas d'unicité conditionnelle)."""
    duplicates = (
        SubmissionFile.objects.filter(is_current=True)
        .values("submission_id", "kind")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    return [
        f"Soumission {row['submission_id']} : {row['total']} fichiers courants ({row['kind']})."
        for row in duplicates
    ]


def check_missing_files() -> list[str]:
    return [
        f"Fichier de soumission {file.pk} absent du disque."
        for file in SubmissionFile.objects.only("pk", "storage_name").iterator()
        if not storage.file_path(file.storage_name).exists()
    ]


def check_reference_sequence() -> list[str]:
    """F4 : par édition, références 1..N sans trou ni doublon, N = valeur du compteur."""
    from apps.conferences.models import Edition

    problems = []
    for edition in Edition.objects.only("pk", "code"):
        counter = Counter.objects.filter(scope=reference_scope(edition)).first()
        value = counter.value if counter else 0
        numbers = sorted(
            int(reference.rsplit("-", 1)[1])
            for reference in Submission.objects.filter(edition=edition)
            .exclude(reference=None)
            .values_list("reference", flat=True)
        )
        if numbers != list(range(1, value + 1)):
            problems.append(
                f"Références {edition.code} : {len(numbers)} attribuées, compteur à {value}."
            )
    return problems
