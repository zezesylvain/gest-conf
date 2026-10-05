"""Espace compte de l'API (``/v1/me…``, plan L1 §9.3). Connecté seulement (permission
par défaut) ; CSRF contrôlé par ``apps.core.authentication.SessionAuthentication``."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.models import Consent
from apps.accounts.serializers import (
    ConsentCreateSerializer,
    ConsentRecordSerializer,
    ConsentsSerializer,
    MeSerializer,
    PreferencesSerializer,
    ProfileSerializer,
    consent_states,
)
from apps.accounts.services.access import editions_with_roles
from apps.accounts.services.invitations import pending_for_user
from apps.core.actor import Actor


def me_payload(user) -> dict:
    editions = [
        {
            "id": access.edition.pk,
            "code": access.edition.code,
            "title_fr": access.edition.title_fr,
            "title_en": access.edition.title_en,
            "year": access.edition.year,
            "status": access.edition.status,
            "roles": [
                {"role": role, "oc_function": oc_function}
                for role, oc_function in sorted(access.roles)
            ],
            "capabilities": sorted(access.capabilities),
            "mfa_required": access.mfa_required,
        }
        for access in editions_with_roles(user).values()
    ]
    return {
        "id": user.pk,
        "email": user.email,
        "locale": user.locale,
        "profile_complete": services.profile_complete(user),
        "privacy_notice_pending": services.privacy_notice_pending(user),
        "editions": editions,
        "pending_invitations": pending_for_user(user),
    }


class MeView(APIView):
    @extend_schema(operation_id="me", responses={200: MeSerializer})
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(me_payload(request.user)).data)


class PreferencesView(APIView):
    @extend_schema(
        operation_id="me_preferences_update",
        request=PreferencesSerializer,
        responses={200: MeSerializer},
    )
    def patch(self, request: Request) -> Response:
        serializer = PreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.set_locale(
            request.user, serializer.validated_data["locale"], actor=Actor.from_request(request)
        )
        return Response(MeSerializer(me_payload(user)).data)


class ProfileView(APIView):
    @extend_schema(operation_id="me_profile", responses={200: ProfileSerializer})
    def get(self, request: Request) -> Response:
        return Response(ProfileSerializer(services.get_profile(request.user)).data)

    @extend_schema(
        operation_id="me_profile_update",
        request=ProfileSerializer,
        responses={200: ProfileSerializer},
    )
    def patch(self, request: Request) -> Response:
        serializer = ProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        profile = services.update_profile(
            request.user, serializer.validated_data, actor=Actor.from_request(request)
        )
        return Response(ProfileSerializer(profile).data)


class ConsentsView(APIView):
    @extend_schema(operation_id="me_consents", responses={200: ConsentsSerializer})
    def get(self, request: Request) -> Response:
        history = Consent.objects.filter(user=request.user).order_by("-recorded_at", "-id")
        payload = {
            "states": consent_states(services.current_consents(request.user)),
            "history": ConsentRecordSerializer(history, many=True).data,
        }
        return Response(ConsentsSerializer(payload).data)

    @extend_schema(
        operation_id="me_consents_create",
        request=ConsentCreateSerializer,
        responses={201: ConsentRecordSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ConsentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        consent = services.record_consent(
            request.user,
            data["kind"],
            data["granted"],
            source=data["source"],
            actor=Actor.from_request(request),
        )
        return Response(ConsentRecordSerializer(consent).data, status=201)
