"""Services de l'édition : fuseau (D13), ordre des dates clés, statut (§6.3), RG-17."""

import datetime as dt

import pytest
from django.core.exceptions import ValidationError

from apps.conferences import services
from apps.conferences.models import Edition, EditionStatus, KeyDate
from apps.conferences.tests.factories import (
    EditionFactory,
    KeyDateFactory,
    SubmissionTypeFactory,
    TrackFactory,
)
from apps.conferences.validators import validate_edition_code, validate_timezone
from apps.core.actor import Actor
from apps.core.errors import Invalid, RuleViolation
from apps.core.models import AuditLog

pytestmark = pytest.mark.django_db

COMMAND = Actor.command("cli:operateur")
SYSTEM = Actor.system("job:test")
UTC = dt.UTC


def ready_edition(**fields) -> Edition:
    """Édition remplissant toutes les préconditions de publication."""
    edition = EditionFactory(**fields)
    TrackFactory(edition=edition)
    SubmissionTypeFactory(edition=edition)
    KeyDateFactory(edition=edition, code="call_open", at=dt.datetime(2027, 1, 10, tzinfo=UTC))
    KeyDateFactory(edition=edition, code="call_close", at=dt.datetime(2027, 3, 31, tzinfo=UTC))
    return edition


# --- Fuseau horaire (D13) -------------------------------------------------------------------


def test_local_to_utc_abidjan_is_utc():
    value = services.local_to_utc(dt.datetime(2027, 3, 31, 23, 59), "Africa/Abidjan")
    assert value == dt.datetime(2027, 3, 31, 23, 59, tzinfo=UTC)


def test_local_to_utc_paris_summer_and_winter():
    summer = services.local_to_utc(dt.datetime(2027, 7, 1, 12, 0), "Europe/Paris")
    winter = services.local_to_utc(dt.datetime(2027, 1, 1, 12, 0), "Europe/Paris")
    assert summer == dt.datetime(2027, 7, 1, 10, 0, tzinfo=UTC)
    assert winter == dt.datetime(2027, 1, 1, 11, 0, tzinfo=UTC)
    assert services.utc_to_local(summer, "Europe/Paris") == dt.datetime(2027, 7, 1, 12, 0)


def test_local_to_utc_rejects_nonexistent_time():
    """Passage à l'heure d'été à Paris le 28 mars 2027 : 02:30 n'existe pas."""
    with pytest.raises(Invalid) as error:
        services.local_to_utc(dt.datetime(2027, 3, 28, 2, 30), "Europe/Paris")
    assert "at_local" in error.value.fields


def test_local_to_utc_rejects_ambiguous_time():
    """Retour à l'heure d'hiver le 31 octobre 2027 : 02:30 existe deux fois."""
    with pytest.raises(Invalid):
        services.local_to_utc(dt.datetime(2027, 10, 31, 2, 30), "Europe/Paris")


def test_local_to_utc_rejects_aware_value():
    with pytest.raises(Invalid):
        services.local_to_utc(dt.datetime(2027, 1, 1, tzinfo=UTC), "Europe/Paris")


def test_key_date_entered_in_edition_timezone():
    edition = EditionFactory(timezone="Europe/Paris")
    key_date = services.create_key_date(
        edition, {"code": "call_open", "at_local": dt.datetime(2027, 1, 10, 9, 0)}, actor=COMMAND
    )
    assert key_date.at == dt.datetime(2027, 1, 10, 8, 0, tzinfo=UTC)


# --- Validateurs ------------------------------------------------------------------------------


@pytest.mark.parametrize("code", ["GC27", "AB", "X2027ABCDEFG"])
def test_edition_code_valid(code):
    validate_edition_code(code)


@pytest.mark.parametrize("code", ["gc27", "G", "27GC", "GC-27", "ABCDEFGHIJKLM"])
def test_edition_code_invalid(code):
    with pytest.raises(ValidationError):
        validate_edition_code(code)


def test_invalid_timezone_rejected():
    with pytest.raises(ValidationError):
        validate_timezone("Mars/Olympus")
    validate_timezone("Africa/Abidjan")


def test_create_edition_with_invalid_timezone_is_refused():
    conference = EditionFactory().conference
    with pytest.raises(Invalid) as error:
        services.create_edition(
            conference=conference,
            actor=COMMAND,
            code="GC99",
            slug="edition-99",
            year=2099,
            title_fr="Édition 99",
            timezone="Mars/Olympus",
        )
    assert "timezone" in error.value.fields


# --- Ordre des dates clés (§3.4) ------------------------------------------------------------


def test_call_close_must_follow_call_open_strictly():
    edition = EditionFactory()
    services.create_key_date(
        edition, {"code": "call_open", "at_local": dt.datetime(2027, 1, 10)}, actor=COMMAND
    )
    with pytest.raises(Invalid):
        services.create_key_date(
            edition, {"code": "call_close", "at_local": dt.datetime(2027, 1, 10)}, actor=COMMAND
        )
    services.create_key_date(
        edition, {"code": "call_close", "at_local": dt.datetime(2027, 3, 31)}, actor=COMMAND
    )
    # Maillons suivants : « ≤ » toléré.
    services.create_key_date(
        edition,
        {"code": "review_deadline", "at_local": dt.datetime(2027, 3, 31)},
        actor=COMMAND,
    )


def test_update_key_date_rechecks_order():
    edition = ready_edition()
    call_open = edition.key_dates.get(code="call_open")
    with pytest.raises(Invalid):
        services.update_key_date(call_open, {"at_local": dt.datetime(2027, 4, 1)}, actor=COMMAND)


def test_free_code_requires_label_and_codes_are_unique():
    edition = EditionFactory()
    with pytest.raises(Invalid) as error:
        services.create_key_date(
            edition, {"code": "atelier", "at_local": dt.datetime(2027, 2, 1)}, actor=COMMAND
        )
    assert "label_fr" in error.value.fields
    services.create_key_date(
        edition,
        {"code": "atelier", "at_local": dt.datetime(2027, 2, 1), "label_fr": "Atelier"},
        actor=COMMAND,
    )
    with pytest.raises(Invalid) as error:
        services.create_key_date(
            edition,
            {"code": "atelier", "at_local": dt.datetime(2027, 2, 2), "label_fr": "Atelier"},
            actor=COMMAND,
        )
    assert "code" in error.value.fields


# --- Statut (§6.3) ----------------------------------------------------------------------------


def test_publication_requires_preconditions():
    edition = EditionFactory(title_en="")
    with pytest.raises(RuleViolation) as error:
        services.set_edition_status(edition, EditionStatus.PUBLISHED, actor=COMMAND)
    assert error.value.code == "edition_incomplete"
    assert {"title_en", "tracks", "submission_types", "key_dates"} <= set(error.value.fields)


def test_publication_is_audited_and_dated():
    edition = ready_edition()
    edition = services.set_edition_status(edition, EditionStatus.PUBLISHED, actor=COMMAND)
    assert edition.status == EditionStatus.PUBLISHED
    assert edition.published_at is not None
    entry = AuditLog.objects.get(action="edition.status_changed")
    assert (entry.before, entry.after) == ({"status": "draft"}, {"status": "published"})
    assert entry.edition == edition


def test_backward_transition_only_by_command_with_reason():
    edition = ready_edition(status=EditionStatus.PUBLISHED)
    with pytest.raises(RuleViolation) as error:
        services.set_edition_status(edition, EditionStatus.DRAFT, actor=SYSTEM)
    assert error.value.code == "invalid_transition"
    with pytest.raises(Invalid):
        services.set_edition_status(edition, EditionStatus.DRAFT, actor=COMMAND)
    edition = services.set_edition_status(
        edition, EditionStatus.DRAFT, actor=COMMAND, reason="Erreur de publication"
    )
    assert edition.status == EditionStatus.DRAFT


def test_archive_only_after_end_date():
    edition = ready_edition(status=EditionStatus.PUBLISHED, end_date=dt.date(2027, 6, 3))
    with pytest.raises(RuleViolation):
        services.set_edition_status(
            edition, EditionStatus.ARCHIVED, actor=SYSTEM, today=dt.date(2027, 6, 3)
        )
    edition = services.set_edition_status(
        edition, EditionStatus.ARCHIVED, actor=SYSTEM, today=dt.date(2027, 6, 4)
    )
    assert edition.is_archived
    assert edition.archived_at is not None


def test_archived_edition_is_read_only_except_by_command():
    edition = EditionFactory(status=EditionStatus.ARCHIVED)
    with pytest.raises(RuleViolation) as error:
        services.update_edition(edition, {"venue": "Palais"}, actor=SYSTEM)
    assert error.value.code == "edition_archived"
    with pytest.raises(RuleViolation):
        services.create_track(edition, {"code": "t1", "name_fr": "T", "name_en": "T"}, actor=SYSTEM)
    services.update_edition(edition, {"venue": "Palais"}, actor=COMMAND)


# --- RG-17 : journalisation --------------------------------------------------------------


def test_rg17_confidentiality_change_logged():
    """RG-17 : le passage du double aveugle est journalisé avec avant/après."""
    edition = EditionFactory(double_blind=True)
    services.update_confidentiality(
        edition, {"double_blind": False, "reviewers_per_submission": 3}, actor=COMMAND
    )
    entry = AuditLog.objects.get(action="edition.confidentiality_changed")
    assert entry.before["double_blind"] is True
    assert entry.after["double_blind"] is False
    assert "reviewers_per_submission" in entry.after


def test_rg17_unchanged_values_write_no_audit_entry():
    edition = EditionFactory(venue="Palais")
    services.update_edition(edition, {"venue": "Palais"}, actor=COMMAND)
    assert not AuditLog.objects.filter(action="edition.updated").exists()


def test_unknown_field_refused():
    edition = EditionFactory()
    with pytest.raises(Invalid) as error:
        services.update_edition(edition, {"status": "published"}, actor=COMMAND)
    assert "status" in error.value.fields


def test_set_current_edition_of_another_conference_refused():
    from apps.conferences.tests.factories import ConferenceFactory

    other = ConferenceFactory(slug="autre")
    with pytest.raises(Invalid):
        services.set_current_edition(other, EditionFactory(), actor=COMMAND)


# --- Appel ouvert ----------------------------------------------------------------------------


def test_is_call_open_bounds():
    edition = ready_edition(status=EditionStatus.PUBLISHED)
    opens = dt.datetime(2027, 1, 10, tzinfo=UTC)
    closes = dt.datetime(2027, 3, 31, tzinfo=UTC)
    assert not services.is_call_open(edition, opens - dt.timedelta(seconds=1))
    assert services.is_call_open(edition, opens)
    assert not services.is_call_open(edition, closes)


def test_call_never_open_on_draft():
    edition = ready_edition()
    assert not services.is_call_open(edition, dt.datetime(2027, 2, 1, tzinfo=UTC))


def test_delete_key_date_audited():
    edition = ready_edition()
    services.delete_key_date(edition.key_dates.get(code="call_close"), actor=COMMAND)
    assert not KeyDate.objects.filter(edition=edition, code="call_close").exists()
    assert AuditLog.objects.filter(action="key_date.deleted", edition=edition).exists()
