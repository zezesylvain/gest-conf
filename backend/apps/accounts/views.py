"""Espace compte de l'API (``/v1/me…``, plan L1 §9.3). Connecté seulement (permission
par défaut) ; CSRF contrôlé par ``apps.core.authentication.SessionAuthentication``."""

from __future__ import annotations

from django.contrib.auth import logout
from django.http import Http404, HttpRequest
from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services
from apps.accounts.models import Consent
from apps.accounts.permissions import RecentAuthRequired, session_has_mfa
from apps.accounts.serializers import (
    AnonymizationSerializer,
    ConsentCreateSerializer,
    ConsentRecordSerializer,
    ConsentsSerializer,
    MeSerializer,
    PreferencesSerializer,
    ProfileSerializer,
    TotpQrSerializer,
    consent_states,
)
from apps.accounts.services.access import editions_with_roles
from apps.accounts.services.invitations import pending_for_user
from apps.accounts.services.mfa import mfa_enabled, totp_qr_data_url
from apps.accounts.services.personal_data import anonymize_user, export_user_data
from apps.core.actor import Actor
from apps.core.errors import Invalid


def me_payload(user, request: Request | HttpRequest) -> dict:
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
        "mfa_enabled": mfa_enabled(user),
        "mfa_verified": session_has_mfa(request),
    }


class MeView(APIView):
    @extend_schema(operation_id="me", responses={200: MeSerializer})
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(me_payload(request.user, request)).data)


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
        return Response(MeSerializer(me_payload(user, request)).data)


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


class TotpQrView(APIView):
    """``GET /v1/me/totp-qr`` : QR code du secret TOTP en attente (plan L1 §10.2).

    Le secret est celui qu'allauth a mis en session au ``GET …/authenticators/totp`` ;
    404 sans secret en attente. Jamais mis en cache.
    """

    @extend_schema(operation_id="me_totp_qr", responses={200: TotpQrSerializer})
    def get(self, request: Request) -> Response:
        qr_code = totp_qr_data_url(request)
        if qr_code is None:
            raise Http404
        response = Response(TotpQrSerializer({"qr_code": qr_code}).data)
        response["Cache-Control"] = "no-store"
        return response


class DataExportView(APIView):
    """``GET /v1/me/data-export`` : toutes ses données en JSON (plan L1 §4.9), sans secret.
    Réauthentification récente, limite ``data_export``, audit ``account.exported``."""

    permission_classes = (*APIView.permission_classes, RecentAuthRequired)
    throttle_scope = "data_export"

    @extend_schema(
        operation_id="me_data_export",
        responses={200: OpenApiResponse(OpenApiTypes.OBJECT, description="Export JSON.")},
    )
    def get(self, request: Request) -> Response:
        data = export_user_data(request.user, actor=Actor.from_request(request))
        response = Response(data)
        response["Content-Disposition"] = (
            f'attachment; filename="gestconf-donnees-{request.user.pk}.json"'
        )
        response["Cache-Control"] = "no-store"
        return response


class AnonymizationView(APIView):
    """``POST /v1/me/anonymization`` : anonymisation immédiate et définitive (plan §4.9).

    Réauthentification récente, adresse du compte saisie pour confirmer, limite
    ``account_deletion``. Refusée (409 ``account_has_active_duties``) tant que des rôles
    de gestion sont actifs. La session est fermée.
    """

    permission_classes = (*APIView.permission_classes, RecentAuthRequired)
    throttle_scope = "account_deletion"

    @extend_schema(
        operation_id="me_anonymization",
        request=AnonymizationSerializer,
        responses={204: None},
    )
    def post(self, request: Request) -> Response:
        serializer = AnonymizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        confirmation = serializer.validated_data["confirmation"].strip().lower()
        if confirmation != request.user.email.lower():
            raise Invalid(
                fields={"confirmation": [_("Saisissez exactement l'adresse de votre compte.")]}
            )
        anonymize_user(request.user, actor=Actor.from_request(request))
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)
