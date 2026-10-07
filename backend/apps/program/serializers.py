"""Sérialiseurs du programme (plan L5 §4). Les réponses publiques et « Mon passage » (L5.4)
sont construites par liste blanche depuis l'instantané publié, jamais depuis le brouillon."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from apps.accounts.services.invitations import display_name
from apps.conferences.models import Edition
from apps.conferences.serializers import LocalDateTimeField
from apps.conferences.services import utc_to_local
from apps.program.models import (
    Equipment,
    Room,
    Session,
    SessionKind,
    SessionRoleKind,
)


class ProgramSettingsSerializer(serializers.ModelSerializer):
    """Paramètres du programme de l'édition (I17) : tampon entre créneaux (RG-13) et RG-11,
    sans effet avant le lot L6."""

    class Meta:
        model = Edition
        fields = ("session_buffer_minutes", "presenter_registration_required")


# --- Gestion du programme (plan L5 §4) -----------------------------------------------------
# Lecture ``program.read``, écriture ``program.write``. Personnes : nom et institution,
# jamais d'adresse. Heures : UTC (``starts_at``) et heure locale de l'édition pour la saisie
# (``starts_local``, D13).


class ProgramPersonSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    institution = serializers.CharField()


def person(user) -> dict | None:
    if user is None:
        return None
    profile = getattr(user, "profile", None)
    return {
        "id": user.pk,
        "name": display_name(user),
        "institution": profile.institution if profile else "",
    }


class RoomSerializer(serializers.ModelSerializer):
    equipment = serializers.ListField(child=serializers.ChoiceField(choices=Equipment.choices))

    class Meta:
        model = Room
        fields = (
            "id",
            "name",
            "capacity",
            "equipment",
            "note",
            "is_accessible",
            "access_note",
            "is_active",
            "position",
        )
        read_only_fields = ("id",)


class RoomWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    capacity = serializers.IntegerField(
        min_value=0, max_value=100_000, allow_null=True, required=False
    )
    equipment = serializers.ListField(
        child=serializers.ChoiceField(choices=Equipment.choices), required=False
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    is_accessible = serializers.BooleanField(required=False)
    access_note = serializers.CharField(required=False, allow_blank=True, max_length=255)
    is_active = serializers.BooleanField(required=False)
    position = serializers.IntegerField(min_value=0, max_value=32767, required=False)


class ScheduledSubmissionSerializer(serializers.Serializer):
    """Communication placée ou à programmer : présentateurs **nommés**, sans adresse."""

    id = serializers.IntegerField()
    reference = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    status = serializers.CharField()
    submission_type = serializers.CharField(allow_null=True)
    track = serializers.CharField(allow_null=True)
    default_duration_min = serializers.IntegerField()
    presenters = serializers.ListField(child=serializers.CharField())
    confirmed = serializers.BooleanField(help_text="Présentateurs désignés par l'auteur (I5).")
    presenter_registered = serializers.BooleanField(
        allow_null=True,
        help_text="Un présentateur au moins est inscrit (RG-11) ; nul sans les inscriptions.",
    )


def scheduled_submission(submission, registered: frozenset[str] | None = None) -> dict:
    from apps.program.services.planning import (
        DEFAULT_SLOT_MINUTES,
        presenter_registered,
        presenters,
    )

    kind = submission.submission_type
    return {
        "id": submission.pk,
        "reference": submission.reference,
        "title": submission.title,
        "status": submission.status,
        "submission_type": kind.code if kind else None,
        "track": submission.track.code if submission.track else None,
        "default_duration_min": (kind.default_duration_min if kind else None)
        or DEFAULT_SLOT_MINUTES,
        "presenters": [
            f"{author.first_name} {author.last_name}".strip() for author in presenters(submission)
        ],
        "confirmed": getattr(submission, "presentation_confirmation", None) is not None,
        "presenter_registered": None
        if registered is None
        else presenter_registered(submission, registered),
    }


class SlotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    position = serializers.IntegerField()
    duration_min = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    submission = ScheduledSubmissionSerializer(allow_null=True)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    speaker = ProgramPersonSerializer(allow_null=True)


class SessionRoleSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=SessionRoleKind.choices)
    person = ProgramPersonSerializer()


class SessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=SessionKind.choices)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    description_fr = serializers.CharField()
    description_en = serializers.CharField()
    track = serializers.CharField(allow_null=True, help_text="Code de la thématique.")
    room = serializers.IntegerField(allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    starts_local = serializers.CharField(help_text="Début à l'heure de l'édition, sans fuseau.")
    ends_local = serializers.CharField(help_text="Fin à l'heure de l'édition, sans fuseau.")
    instructions = serializers.CharField()
    slots = SlotSerializer(many=True)
    roles = SessionRoleSerializer(many=True)


def session_data(session: Session, registered: frozenset[str] | None = None) -> dict:
    zone = session.edition.timezone
    return {
        "id": session.pk,
        "kind": session.kind,
        "title_fr": session.title_fr,
        "title_en": session.title_en,
        "description_fr": session.description_fr,
        "description_en": session.description_en,
        "track": session.track.code if session.track else None,
        "room": session.room_id,
        "starts_at": session.starts_at,
        "ends_at": session.ends_at,
        "starts_local": utc_to_local(session.starts_at, zone).isoformat(),
        "ends_local": utc_to_local(session.ends_at, zone).isoformat(),
        "instructions": session.instructions,
        "slots": [
            {
                "id": slot.pk,
                "position": slot.position,
                "duration_min": slot.duration_min,
                "starts_at": slot.starts_at,
                "ends_at": slot.ends_at,
                "submission": scheduled_submission(slot.submission, registered)
                if slot.submission
                else None,
                "title_fr": slot.title_fr,
                "title_en": slot.title_en,
                "speaker": person(slot.speaker),
            }
            for slot in sorted(session.slots.all(), key=lambda item: (item.position, item.pk))
        ],
        "roles": [
            {"id": item.pk, "role": item.role, "person": person(item.user)}
            for item in session.roles.all()
        ],
    }


# Types de conflits (RG-12, RG-13) : énumération « ProgramConflictKind » du schéma.
PROGRAM_CONFLICT_CHOICES = [
    ("room", "room"),
    ("person", "person"),
    ("overflow", "overflow"),
    ("registration", "registration"),
]


class ProgramConflictSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PROGRAM_CONFLICT_CHOICES)
    sessions = serializers.ListField(child=serializers.IntegerField())
    slots = serializers.ListField(child=serializers.IntegerField())
    person = serializers.CharField(
        help_text="Nom de la personne (conflit de personne) ou des présentateurs (RG-11)."
    )
    minutes = serializers.IntegerField(help_text="Dépassement en minutes (RG-13).")


class ProgramBoardSerializer(serializers.Serializer):
    """Brouillon complet pour le planificateur (I15) : à chaque écriture, la gestion reçoit
    la nouvelle révision, les sessions et les conflits (I14)."""

    revision = serializers.IntegerField()
    published_revision = serializers.IntegerField()
    published_version = serializers.IntegerField()
    unpublished_changes = serializers.BooleanField()
    timezone = serializers.CharField()
    days = serializers.ListField(child=serializers.DateField())
    buffer_minutes = serializers.IntegerField()
    rooms = RoomSerializer(many=True)
    sessions = SessionSerializer(many=True)
    to_schedule = ScheduledSubmissionSerializer(many=True)
    conflicts = ProgramConflictSerializer(many=True)


class SessionWriteSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SessionKind.choices, required=False)
    title_fr = serializers.CharField(max_length=255, required=False)
    title_en = serializers.CharField(max_length=255, required=False, allow_blank=True)
    description_fr = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    description_en = serializers.CharField(required=False, allow_blank=True, max_length=5000)
    track = serializers.CharField(required=False, allow_null=True, help_text="Code.")
    room = serializers.IntegerField(required=False, allow_null=True)
    starts_local = LocalDateTimeField(required=False)
    ends_local = LocalDateTimeField(required=False)
    instructions = serializers.CharField(required=False, allow_blank=True, max_length=5000)


class SlotCreateSerializer(serializers.Serializer):
    """Une communication (``submission``) **ou** un élément libre (``title_fr``)."""

    submission = serializers.IntegerField(required=False)
    title_fr = serializers.CharField(max_length=300, required=False)
    title_en = serializers.CharField(max_length=300, required=False, allow_blank=True)
    speaker = serializers.IntegerField(required=False, allow_null=True)
    duration_min = serializers.IntegerField(min_value=1, max_value=600, required=False)
    position = serializers.IntegerField(min_value=0, required=False)

    def validate(self, attrs):
        if ("submission" in attrs) == ("title_fr" in attrs):
            raise serializers.ValidationError(
                {"submission": _("Une communication ou un titre libre, l'un ou l'autre.")}
            )
        return attrs


class SlotUpdateSerializer(serializers.Serializer):
    """Durée ; déplacement (``session``, ``position``) ; titres et intervenant d'un élément
    libre."""

    duration_min = serializers.IntegerField(min_value=1, max_value=600, required=False)
    session = serializers.IntegerField(required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    title_fr = serializers.CharField(max_length=300, required=False)
    title_en = serializers.CharField(max_length=300, required=False, allow_blank=True)
    speaker = serializers.IntegerField(required=False, allow_null=True)


class SessionRoleWriteSerializer(serializers.Serializer):
    user = serializers.IntegerField()
    role = serializers.ChoiceField(choices=SessionRoleKind.choices)


class PersonSearchSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    institution = serializers.CharField()
    roles = serializers.ListField(child=serializers.CharField())


def board_data(edition: Edition) -> dict:
    """Brouillon complet (planificateur, I15) : sessions, salles, liste « à programmer »,
    conflits (RG-12, RG-13) et révision (I14). Requêtes en nombre constant."""
    import datetime as dt

    from apps.program.services import planning

    state = planning.program_state(edition)
    sessions = list(planning.program_sessions(edition))
    conflicts = planning.detect_conflicts(edition, sessions)
    registered = planning.registered_people(edition)
    if edition.start_date and edition.end_date:
        count = (edition.end_date - edition.start_date).days + 1
        days = [edition.start_date + dt.timedelta(days=offset) for offset in range(count)]
    else:
        zone = edition.timezone
        days = sorted({utc_to_local(item.starts_at, zone).date() for item in sessions})
    return {
        "revision": state.revision,
        "published_revision": state.published_revision,
        "published_version": state.published_version,
        "unpublished_changes": state.revision != state.published_revision,
        "timezone": edition.timezone,
        "days": days,
        "buffer_minutes": edition.session_buffer_minutes,
        "rooms": RoomSerializer(Room.objects.filter(edition=edition), many=True).data,
        "sessions": [session_data(item, registered) for item in sessions],
        "to_schedule": [
            scheduled_submission(item, registered) for item in planning.to_schedule(edition)
        ],
        "conflicts": [
            {
                "kind": item.kind,
                "sessions": list(item.sessions),
                "slots": list(item.slots),
                "person": item.person,
                "minutes": item.minutes,
            }
            for item in conflicts
        ],
    }


# --- Programme public (I7) et « Mon passage » (I8) ------------------------------------------
# Construits par liste blanche depuis l'instantané publié : ni clé de personne, ni identifiant
# de communication, ni consignes internes, ni adresse.


def public_session(session: dict) -> dict:
    return {
        "id": session["id"],
        "kind": session["kind"],
        "title_fr": session["title_fr"],
        "title_en": session["title_en"],
        "description_fr": session["description_fr"],
        "description_en": session["description_en"],
        "track": session["track"],
        "room": {
            "name": session["room"]["name"],
            "is_accessible": session["room"]["is_accessible"],
            "access_note": session["room"]["access_note"],
        }
        if session["room"]
        else None,
        "starts_at": session["starts_at"],
        "ends_at": session["ends_at"],
        "chairs": [
            {"role": role["role"], "name": role["name"], "institution": role["institution"]}
            for role in session["roles"]
        ],
        "slots": [
            {
                "id": slot["id"],
                "starts_at": slot["starts_at"],
                "ends_at": slot["ends_at"],
                "duration_min": slot["duration_min"],
                "reference": (slot["submission"] or {}).get("reference"),
                "title": slot["submission"]["title"] if slot["submission"] else slot["title_fr"],
                "title_en": "" if slot["submission"] else slot["title_en"],
                "type": (slot["submission"] or {}).get("type"),
                "authors": [
                    {
                        "name": author["name"],
                        "institution": author["institution"],
                        "presenter": author["presenter"],
                    }
                    for author in (slot["submission"] or {}).get("authors", [])
                ],
                "speaker": {
                    "name": slot["speaker"]["name"],
                    "institution": slot["speaker"]["institution"],
                    "bio": slot["speaker"].get("bio", ""),
                    "photo_url": slot["speaker"].get("photo_url"),
                }
                if slot["speaker"]
                else None,
            }
            for slot in session["slots"]
        ],
    }


def public_speakers(publication) -> dict:
    """Intervenants invités de la dernière publication (plan L8, N6) : les orateurs des
    créneaux libres, réunis par personne, avec leurs passages. **Liste blanche** de
    l'instantané : nom, établissement, biographie et photo déjà filtrées par les
    consentements de L2 à la publication (I11) ; jamais la clé du compte."""
    snapshot = publication.snapshot
    people: dict[str, dict] = {}
    for session in snapshot["sessions"]:
        for slot in session["slots"]:
            speaker = slot.get("speaker")
            if not speaker:
                continue
            person = people.setdefault(
                speaker["key"],
                {
                    "name": speaker["name"],
                    "institution": speaker["institution"],
                    "bio": speaker.get("bio", ""),
                    "photo_url": speaker.get("photo_url"),
                    "talks": [],
                },
            )
            person["talks"].append(
                {
                    "session_id": session["id"],
                    "session_title_fr": session["title_fr"],
                    "session_title_en": session["title_en"],
                    "title_fr": slot["title_fr"],
                    "title_en": slot["title_en"],
                    "starts_at": slot["starts_at"],
                    "ends_at": slot["ends_at"],
                    "room": session["room"]["name"] if session["room"] else None,
                }
            )
    speakers = sorted(people.values(), key=lambda item: item["name"].casefold())
    for person in speakers:
        person["talks"].sort(key=lambda talk: talk["starts_at"])
    return {"timezone": snapshot["edition"]["timezone"], "speakers": speakers}


def local_day(value: str, tz_name: str) -> str:
    import datetime as dt
    from zoneinfo import ZoneInfo

    return dt.datetime.fromisoformat(value).astimezone(ZoneInfo(tz_name)).date().isoformat()


def public_summary(publication) -> dict:
    """Accueil du programme : jours et sessions, sans le détail des communications (bilan
    de L5.0 : une page par jour et par session)."""
    snapshot = publication.snapshot
    zone = snapshot["edition"]["timezone"]
    days: dict[str, list] = {}
    for session in snapshot["sessions"]:
        days.setdefault(local_day(session["starts_at"], zone), []).append(
            {
                "id": session["id"],
                "kind": session["kind"],
                "title_fr": session["title_fr"],
                "title_en": session["title_en"],
                "track": session["track"],
                "room": session["room"]["name"] if session["room"] else None,
                "starts_at": session["starts_at"],
                "ends_at": session["ends_at"],
                "slot_count": len(session["slots"]),
            }
        )
    return {
        "edition": snapshot["edition"]["code"],
        "version": publication.version,
        "published_at": publication.published_at,
        "timezone": zone,
        "days": [{"date": day, "sessions": days[day]} for day in sorted(days)],
    }


class PublicProgramTrackSerializer(serializers.Serializer):
    code = serializers.CharField()
    name_fr = serializers.CharField()
    name_en = serializers.CharField()


class PublicProgramTypeSerializer(serializers.Serializer):
    code = serializers.CharField()
    label_fr = serializers.CharField()
    label_en = serializers.CharField()


class PublicProgramRoomSerializer(serializers.Serializer):
    name = serializers.CharField()
    is_accessible = serializers.BooleanField()
    access_note = serializers.CharField()


class PublicProgramAuthorSerializer(serializers.Serializer):
    name = serializers.CharField()
    institution = serializers.CharField()
    presenter = serializers.BooleanField()


class PublicProgramSpeakerSerializer(serializers.Serializer):
    name = serializers.CharField()
    institution = serializers.CharField()
    bio = serializers.CharField()
    photo_url = serializers.CharField(allow_null=True)


class PublicProgramChairSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=SessionRoleKind.choices)
    name = serializers.CharField()
    institution = serializers.CharField()


class PublicProgramSlotSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    duration_min = serializers.IntegerField()
    reference = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    title_en = serializers.CharField()
    type = PublicProgramTypeSerializer(allow_null=True)
    authors = PublicProgramAuthorSerializer(many=True)
    speaker = PublicProgramSpeakerSerializer(allow_null=True)


class PublicSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=SessionKind.choices)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    description_fr = serializers.CharField()
    description_en = serializers.CharField()
    track = PublicProgramTrackSerializer(allow_null=True)
    room = PublicProgramRoomSerializer(allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    chairs = PublicProgramChairSerializer(many=True)
    slots = PublicProgramSlotSerializer(many=True)


class PublicProgramSessionSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=SessionKind.choices)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    track = PublicProgramTrackSerializer(allow_null=True)
    room = serializers.CharField(allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    slot_count = serializers.IntegerField()


class PublicProgramDaySummarySerializer(serializers.Serializer):
    date = serializers.DateField()
    sessions = PublicProgramSessionSummarySerializer(many=True)


class PublicProgramSerializer(serializers.Serializer):
    edition = serializers.CharField()
    version = serializers.IntegerField()
    published_at = serializers.DateTimeField()
    timezone = serializers.CharField()
    days = PublicProgramDaySummarySerializer(many=True)


class PublicSpeakerTalkSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    session_title_fr = serializers.CharField()
    session_title_en = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    room = serializers.CharField(allow_null=True)


class PublicSpeakerProfileSerializer(serializers.Serializer):
    name = serializers.CharField()
    institution = serializers.CharField()
    bio = serializers.CharField()
    photo_url = serializers.CharField(allow_null=True)
    talks = PublicSpeakerTalkSerializer(many=True)


class PublicSpeakersSerializer(serializers.Serializer):
    timezone = serializers.CharField()
    speakers = PublicSpeakerProfileSerializer(many=True)


class PublicProgramDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    timezone = serializers.CharField()
    sessions = PublicSessionSerializer(many=True)


class AgendaEditionSerializer(serializers.Serializer):
    code = serializers.CharField()
    title_fr = serializers.CharField()
    title_en = serializers.CharField()
    timezone = serializers.CharField()


class AgendaSessionSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=SessionKind.choices)
    title_fr = serializers.CharField()
    title_en = serializers.CharField()


class AgendaRoomSerializer(serializers.Serializer):
    name = serializers.CharField()
    access_note = serializers.CharField()
    is_accessible = serializers.BooleanField()


# Rôles d'un passage : présentateur, intervenant invité, rôles de séance.
PASSAGE_ROLE_CHOICES = [
    ("presenter", "presenter"),
    ("speaker", "speaker"),
    *[(value, value) for value in SessionRoleKind.values],
]


class AgendaEntrySerializer(serializers.Serializer):
    """« Mon passage » (I8) : les passages de la personne connectée."""

    edition = AgendaEditionSerializer()
    version = serializers.IntegerField()
    role = serializers.ChoiceField(choices=PASSAGE_ROLE_CHOICES)
    session = AgendaSessionSerializer()
    slot = serializers.IntegerField(allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    duration_min = serializers.IntegerField()
    room = AgendaRoomSerializer()
    title = serializers.CharField()
    title_en = serializers.CharField()
    reference = serializers.CharField()
    co_speakers = serializers.ListField(child=serializers.CharField())
    chairs = serializers.ListField(child=serializers.CharField())
    instructions = serializers.CharField()


class PublicationSerializer(serializers.Serializer):
    version = serializers.IntegerField()
    published_at = serializers.DateTimeField()
    published_by = serializers.CharField()
    summary = serializers.JSONField()
