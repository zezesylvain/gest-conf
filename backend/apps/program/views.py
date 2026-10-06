"""Routes du programme dans la gestion (``v1/manage/editions/{id}/program/…``, plan L5 §4).

Lecture ``program.read`` ; écriture ``program.write`` (CO « programme », administrateur ;
I1). Chaque écriture passe par le service de planification (verrou, révision, journal) et
renvoie le brouillon complet : nouvelle révision, sessions recalculées, conflits (I14, I15).
``If-Match`` porte la révision lue : 412 ``stale_revision`` si un autre membre a modifié le
programme entre-temps.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Q
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.models import User, UserRole, UserRoleStatus
from apps.accounts.permissions import ManageViewSet
from apps.accounts.roles import Capability as C
from apps.conferences.models import Track
from apps.core.actor import Actor
from apps.core.errors import Invalid
from apps.program.models import Room, Session, SessionRole, Slot
from apps.program.serializers import (
    PersonSearchSerializer,
    ProgramBoardSerializer,
    ProgramSettingsSerializer,
    RoomWriteSerializer,
    SessionRoleWriteSerializer,
    SessionWriteSerializer,
    SlotCreateSerializer,
    SlotUpdateSerializer,
    board_data,
    person,
)
from apps.program.services import planning
from apps.program.services import settings as program_settings
from apps.submissions.models import Submission

IF_MATCH = OpenApiParameter(
    "If-Match",
    type=int,
    location=OpenApiParameter.HEADER,
    required=False,
    description="Révision du programme lue ; 412 « stale_revision » si elle a changé (I14).",
)


# Écritures du brouillon (I1) : CO « programme » et administrateur.
WRITES = {
    "create": C.PROGRAM_WRITE,
    "partial_update": C.PROGRAM_WRITE,
    "destroy": C.PROGRAM_WRITE,
}


def expected_revision(request: Request) -> int | None:
    value = request.headers.get("If-Match", "").strip().strip('"')
    if not value:
        return None
    if not value.isdigit():
        raise Invalid(fields={"If-Match": ["Révision entière attendue."]})
    return int(value)


class _ProgramViewSet(ManageViewSet):
    """Base : objets de l'édition visée seulement (404 sinon), réponse « brouillon ». Table
    des capacités explicite dans chaque vue (échec fermé)."""

    def board(self, code: int = status.HTTP_200_OK) -> Response:
        return Response(ProgramBoardSerializer(board_data(self.edition)).data, status=code)

    def actor(self) -> Actor:
        return Actor.from_request(self.request)

    def _member(self, user_id: int | None, field: str) -> User | None:
        """Personne de l'édition (rôle actif) : président de séance, intervenant (I10)."""
        if user_id is None:
            return None
        user = User.objects.filter(
            pk=user_id,
            roles__edition=self.edition,
            roles__status=UserRoleStatus.ACTIVE,
            anonymized_at__isnull=True,
        ).first()
        if user is None:
            raise Invalid(fields={field: ["Personne sans rôle dans l'édition."]})
        return user

    def _room(self, room_id: int | None) -> Room | None:
        if room_id is None:
            return None
        room = Room.objects.filter(pk=room_id, edition=self.edition).first()
        if room is None:
            raise Invalid(fields={"room": ["Salle d'une autre édition."]})
        return room

    def _session(self, session_id: int) -> Session:
        session = (
            Session.objects.filter(pk=session_id, edition=self.edition)
            .select_related("edition")
            .first()
        )
        if session is None:
            raise Http404
        return session


class ProgramSettingsViewSet(ManageViewSet):
    """``…/program/settings`` : paramètres du programme (I17)."""

    serializer_class = ProgramSettingsSerializer
    required_capabilities = {"retrieve": C.PROGRAM_READ, "partial_update": C.PROGRAM_WRITE}

    @extend_schema(operation_id="manage_program_settings_retrieve")
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return Response(ProgramSettingsSerializer(self.edition).data)

    @extend_schema(operation_id="manage_program_settings_update")
    def partial_update(self, request: Request, edition_id: int) -> Response:
        serializer = ProgramSettingsSerializer(self.edition, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        edition = program_settings.update_program_settings(
            self.edition, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(ProgramSettingsSerializer(edition).data)


class ProgramBoardViewSet(_ProgramViewSet):
    """``…/program`` : brouillon complet pour le planificateur."""

    serializer_class = ProgramBoardSerializer
    required_capabilities = {"retrieve": C.PROGRAM_READ}

    @extend_schema(operation_id="manage_program_board", responses={200: ProgramBoardSerializer})
    def retrieve(self, request: Request, edition_id: int) -> Response:
        return self.board()


class RoomViewSet(_ProgramViewSet):
    """``…/program/rooms`` : salles (I9)."""

    serializer_class = RoomWriteSerializer
    required_capabilities = WRITES

    def _object(self, room_id: int) -> Room:
        room = Room.objects.filter(pk=room_id, edition=self.edition).select_related("edition")
        if not room.exists():
            raise Http404
        return room.get()

    @extend_schema(
        operation_id="manage_program_rooms_create",
        parameters=[IF_MATCH],
        request=RoomWriteSerializer,
        responses={201: ProgramBoardSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = RoomWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        planning.create_room(
            self.edition,
            serializer.validated_data,
            actor=self.actor(),
            revision=expected_revision(request),
        )
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_program_rooms_update",
        parameters=[IF_MATCH],
        request=RoomWriteSerializer,
        responses={200: ProgramBoardSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        room = self._object(item_id)
        serializer = RoomWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        planning.update_room(
            room, serializer.validated_data, actor=self.actor(), revision=expected_revision(request)
        )
        return self.board()

    @extend_schema(
        operation_id="manage_program_rooms_delete",
        parameters=[IF_MATCH],
        responses={200: ProgramBoardSerializer},
    )
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        planning.delete_room(
            self._object(item_id), actor=self.actor(), revision=expected_revision(request)
        )
        return self.board()


class SessionViewSet(_ProgramViewSet):
    """``…/program/sessions`` : sessions (I2, I12), saisies à l'heure de l'édition (D13)."""

    serializer_class = SessionWriteSerializer
    required_capabilities = WRITES

    def _values(self, data: dict) -> dict:
        values = dict(data)
        if "room" in values:
            values["room"] = self._room(values["room"])
        if "track" in values:
            code = values["track"]
            if code:
                track = Track.objects.filter(edition=self.edition, code=code).first()
                if track is None:
                    raise Invalid(fields={"track": ["Thématique inconnue."]})
                values["track"] = track
            else:
                values["track"] = None
        return values

    @extend_schema(
        operation_id="manage_program_sessions_create",
        parameters=[IF_MATCH],
        request=SessionWriteSerializer,
        responses={201: ProgramBoardSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = SessionWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        planning.create_session(
            self.edition,
            self._values(serializer.validated_data),
            actor=self.actor(),
            revision=expected_revision(request),
        )
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_program_sessions_update",
        parameters=[IF_MATCH],
        request=SessionWriteSerializer,
        responses={200: ProgramBoardSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        session = self._session(item_id)
        serializer = SessionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        planning.update_session(
            session,
            self._values(serializer.validated_data),
            actor=self.actor(),
            revision=expected_revision(request),
        )
        return self.board()

    @extend_schema(
        operation_id="manage_program_sessions_delete",
        parameters=[IF_MATCH],
        responses={200: ProgramBoardSerializer},
    )
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        planning.delete_session(
            self._session(item_id), actor=self.actor(), revision=expected_revision(request)
        )
        return self.board()


class SlotViewSet(_ProgramViewSet):
    """``…/program/sessions/{s}/slots`` (création) et ``…/program/slots/{c}`` (durée,
    déplacement, titres, retrait)."""

    serializer_class = SlotUpdateSerializer
    required_capabilities = WRITES

    def _slot(self, slot_id: int) -> Slot:
        slot = (
            Slot.objects.filter(pk=slot_id, session__edition=self.edition)
            .select_related("session__edition")
            .first()
        )
        if slot is None:
            raise Http404
        return slot

    @extend_schema(
        operation_id="manage_program_slots_create",
        parameters=[IF_MATCH],
        request=SlotCreateSerializer,
        responses={201: ProgramBoardSerializer},
    )
    def create(self, request: Request, edition_id: int, session_id: int) -> Response:
        session = self._session(session_id)
        serializer = SlotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        revision = expected_revision(request)
        if "submission" in data:
            submission = Submission.objects.filter(
                pk=data["submission"], edition=self.edition
            ).first()
            if submission is None:
                raise Invalid(fields={"submission": ["Communication inconnue."]})
            planning.place_submission(
                session,
                submission,
                actor=self.actor(),
                revision=revision,
                position=data.get("position"),
                duration_min=data.get("duration_min"),
            )
        else:
            planning.add_free_slot(
                session,
                title_fr=data["title_fr"],
                title_en=data.get("title_en", ""),
                speaker=self._member(data.get("speaker"), "speaker"),
                duration_min=data.get("duration_min", planning.DEFAULT_SLOT_MINUTES),
                position=data.get("position"),
                actor=self.actor(),
                revision=revision,
            )
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_program_slots_update",
        parameters=[IF_MATCH],
        request=SlotUpdateSerializer,
        responses={200: ProgramBoardSerializer},
    )
    def partial_update(self, request: Request, edition_id: int, item_id: int) -> Response:
        slot = self._slot(item_id)
        serializer = SlotUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        revision = expected_revision(request)
        target = data.pop("session", None)
        position = data.pop("position", None)
        if "speaker" in data:
            data["speaker"] = self._member(data["speaker"], "speaker")
        with transaction.atomic():
            if data:
                planning.update_slot(slot, data, actor=self.actor(), revision=revision)
                # Révision vérifiée par la première écriture ; le verrou de l'état du
                # programme reste tenu jusqu'à la fin de la transaction.
                revision = None
            if target is not None or position is not None:
                planning.move_slot(
                    slot,
                    session=self._session(target) if target is not None else None,
                    position=position,
                    actor=self.actor(),
                    revision=revision,
                )
        return self.board()

    @extend_schema(
        operation_id="manage_program_slots_delete",
        parameters=[IF_MATCH],
        responses={200: ProgramBoardSerializer},
    )
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        planning.remove_slot(
            self._slot(item_id), actor=self.actor(), revision=expected_revision(request)
        )
        return self.board()


class SessionRoleViewSet(_ProgramViewSet):
    """``…/program/sessions/{s}/roles`` (ajout) et ``…/program/session-roles/{r}`` (retrait)."""

    serializer_class = SessionRoleWriteSerializer
    required_capabilities = {"create": C.PROGRAM_WRITE, "destroy": C.PROGRAM_WRITE}

    @extend_schema(
        operation_id="manage_program_roles_create",
        parameters=[IF_MATCH],
        request=SessionRoleWriteSerializer,
        responses={201: ProgramBoardSerializer},
    )
    def create(self, request: Request, edition_id: int, session_id: int) -> Response:
        session = self._session(session_id)
        serializer = SessionRoleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        planning.add_session_role(
            session,
            self._member(serializer.validated_data["user"], "user"),
            serializer.validated_data["role"],
            actor=self.actor(),
            revision=expected_revision(request),
        )
        return self.board(status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_program_roles_delete",
        parameters=[IF_MATCH],
        responses={200: ProgramBoardSerializer},
    )
    def destroy(self, request: Request, edition_id: int, item_id: int) -> Response:
        item = (
            SessionRole.objects.filter(pk=item_id, session__edition=self.edition)
            .select_related("session__edition")
            .first()
        )
        if item is None:
            raise Http404
        planning.remove_session_role(item, actor=self.actor(), revision=expected_revision(request))
        return self.board()


class ProgramPeopleViewSet(_ProgramViewSet):
    """``…/program/people?q=`` : personnes de l'édition (rôle actif), pour les rôles de
    séance et les intervenants (I10, I11). Nom et institution, jamais d'adresse."""

    serializer_class = PersonSearchSerializer
    queryset = UserRole.objects.none()
    required_capabilities = {"list": C.PROGRAM_WRITE}

    @extend_schema(
        operation_id="manage_program_people",
        parameters=[OpenApiParameter("q", OpenApiTypes.STR, required=False)],
        responses={200: PersonSearchSerializer(many=True)},
    )
    def list(self, request: Request, edition_id: int) -> Response:
        query = request.query_params.get("q", "").strip()[:100]
        roles = UserRole.objects.filter(
            edition=self.edition, status=UserRoleStatus.ACTIVE, user__anonymized_at__isnull=True
        ).select_related("user__profile")
        if query:
            roles = roles.filter(
                Q(user__profile__first_name__icontains=query)
                | Q(user__profile__last_name__icontains=query)
                | Q(user__profile__institution__icontains=query)
            )
        people: dict[int, dict] = {}
        for row in roles.order_by("user__profile__last_name", "user_id")[:200]:
            entry = people.setdefault(row.user_id, {**person(row.user), "roles": []})
            if row.role not in entry["roles"]:
                entry["roles"].append(row.role)
        return Response(PersonSearchSerializer(list(people.values())[:20], many=True).data)
