"""Membres, invitations et journal d'une édition (``/v1/manage/editions/{edition_id}/…``)
et réponse aux invitations (``/v1/invitations/…``) — plan L1 §5.4, §5.7, §7.4, §9.3."""

from __future__ import annotations

import django_filters
from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, mixins, serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.manage_serializers import (
    AuditEntrySerializer,
    InvitationBatchSerializer,
    InvitationCreateSerializer,
    InvitationSerializer,
    InvitationWithEmailSerializer,
    MemberSerializer,
    MemberWithEmailSerializer,
    RevokeSerializer,
)
from apps.accounts.models import InvitationStatus, RoleInvitation, UserRole
from apps.accounts.permissions import (
    ManageViewSet,
    RecentAuthRequired,
    has_recent_authentication,
)
from apps.accounts.roles import REAUTH_REQUIRED_FOR_GRANT, Capability, InvitableRole
from apps.accounts.services import invitations as invitation_services
from apps.accounts.services.access import EditionAccess
from apps.accounts.services.roles import revoke_role
from apps.core.actor import Actor
from apps.core.errors import ErrorCode
from apps.core.models import AuditLog
from apps.core.permissions import CsrfEnforced

C = Capability


def _reauthentication_required() -> exceptions.PermissionDenied:
    return exceptions.PermissionDenied(
        RecentAuthRequired.message, code=ErrorCode.REAUTHENTICATION_REQUIRED.value
    )


def _scope_by_visible_roles(queryset: QuerySet, access: EditionAccess) -> QuerySet:
    """Le SC_CHAIR ne voit que le comité scientifique (§5.4)."""
    visible = access.visible_roles
    return queryset if visible is None else queryset.filter(role__in=visible)


class MemberViewSet(mixins.ListModelMixin, ManageViewSet):
    """``GET …/roles`` et ``POST …/roles/{role_id}/revoke`` (§5.4, §5.5)."""

    queryset = UserRole.objects.select_related("user", "user__profile", "edition").order_by(
        "role", "id"
    )
    required_capabilities = {"list": C.MEMBERS_READ, "revoke": C.MEMBERS_MANAGE}
    pagination_class = None
    lookup_url_kwarg = "role_id"

    def scope_queryset(self, queryset: QuerySet, access: EditionAccess) -> QuerySet:
        return _scope_by_visible_roles(queryset, access)

    def get_serializer_class(self):
        # Adresse visible seulement avec members.manage (minimisation, échec fermé).
        if hasattr(self, "access") and self.access.has(C.MEMBERS_MANAGE):
            return MemberWithEmailSerializer
        return MemberSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.action == "revoke":
            permissions.append(RecentAuthRequired())
        return permissions

    @extend_schema(
        operation_id="manage_members_list", responses={200: MemberWithEmailSerializer(many=True)}
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_member_revoke",
        request=RevokeSerializer,
        responses={200: MemberWithEmailSerializer},
    )
    def revoke(self, request: Request, edition_id: int, role_id: int) -> Response:
        serializer = RevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_role = revoke_role(
            user_role=self.get_object(),
            actor=Actor.from_request(request),
            reason=serializer.validated_data["reason"],
            access=self.access,
        )
        return Response(self.get_serializer_class()(user_role).data)


class InvitationViewSet(mixins.ListModelMixin, ManageViewSet):
    """``…/invitations`` : liste filtrée par rôle, création, renvoi, annulation (§5.7)."""

    queryset = RoleInvitation.objects.select_related(
        "edition", "invited_by", "invited_by__profile"
    ).order_by("-created_at", "-id")
    required_capabilities = {
        "list": C.MEMBERS_READ,
        "create": C.MEMBERS_MANAGE,
        "resend": C.MEMBERS_MANAGE,
        "cancel": C.MEMBERS_MANAGE,
    }
    filter_backends = (DjangoFilterBackend,)
    filterset_fields = ("status", "role")
    lookup_url_kwarg = "invitation_id"

    def scope_queryset(self, queryset: QuerySet, access: EditionAccess) -> QuerySet:
        return _scope_by_visible_roles(queryset, access)

    def get_serializer_class(self):
        if hasattr(self, "access") and self.access.has(C.MEMBERS_MANAGE):
            return InvitationWithEmailSerializer
        return InvitationSerializer

    def get_throttles(self):
        # Limite « invitation_create » sur la seule création : ScopedRateThrottle ne
        # distingue pas les méthodes, et la même vue sert la liste (§4.7).
        if self.action == "create":
            self.throttle_scope = "invitation_create"
            return super().get_throttles()
        return []

    @extend_schema(
        operation_id="manage_invitations_list",
        responses={200: InvitationWithEmailSerializer(many=True)},
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="manage_invitations_create",
        request=InvitationCreateSerializer,
        responses={201: InvitationBatchSerializer},
    )
    def create(self, request: Request, edition_id: int) -> Response:
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        # Inviter un ADMIN ou un CHAIR : réauthentification récente (§5.5, D12).
        if data["role"] in REAUTH_REQUIRED_FOR_GRANT and not has_recent_authentication(request):
            raise _reauthentication_required()
        batch = invitation_services.create_invitations(
            edition=self.edition,
            emails=data["emails"],
            role=data["role"],
            oc_function=data["oc_function"],
            locale=data.get("locale"),
            message=data["message"],
            actor=Actor.from_request(request),
            access=self.access,
        )
        payload = {
            "created": batch.created,
            "skipped": [{"email": email, "reason": reason} for email, reason in batch.skipped],
        }
        return Response(InvitationBatchSerializer(payload).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="manage_invitation_resend",
        request=None,
        responses={200: InvitationWithEmailSerializer},
    )
    def resend(self, request: Request, edition_id: int, invitation_id: int) -> Response:
        invitation = invitation_services.resend(
            self.get_object(), actor=Actor.from_request(request), access=self.access
        )
        return Response(self.get_serializer_class()(invitation).data)

    @extend_schema(
        operation_id="manage_invitation_cancel",
        request=None,
        responses={200: InvitationWithEmailSerializer},
    )
    def cancel(self, request: Request, edition_id: int, invitation_id: int) -> Response:
        invitation = invitation_services.cancel(
            self.get_object(), actor=Actor.from_request(request), access=self.access
        )
        return Response(self.get_serializer_class()(invitation).data)


class AuditFilter(django_filters.FilterSet):
    """Filtres explicites (§5.3) : action (exacte ou préfixe « domaine. »), acteur,
    type d'objet, période."""

    action = django_filters.CharFilter(method="filter_action")
    actor = django_filters.NumberFilter(field_name="actor_id")
    object_type = django_filters.CharFilter(field_name="object_type")
    since = django_filters.IsoDateTimeFilter(field_name="at", lookup_expr="gte")
    until = django_filters.IsoDateTimeFilter(field_name="at", lookup_expr="lt")

    class Meta:
        model = AuditLog
        fields = ("action", "actor", "object_type", "since", "until")

    def filter_action(self, queryset, name, value):
        if value.endswith("."):
            return queryset.filter(action__startswith=value)
        return queryset.filter(action=value)


class AuditViewSet(mixins.ListModelMixin, ManageViewSet):
    """``GET …/audit`` : journal de l'édition, sans IP ni navigateur ; lecture seule (§7.4).

    Les entrées sans édition (connexions, comptes) ne sont visibles que par ``audit_query``.
    """

    queryset = AuditLog.objects.select_related("actor", "actor__profile").order_by("-at", "-id")
    serializer_class = AuditEntrySerializer
    required_capabilities = {"list": C.AUDIT_READ}
    filter_backends = (DjangoFilterBackend,)
    filterset_class = AuditFilter

    @extend_schema(operation_id="manage_audit_list")
    def list(self, request: Request, *args, **kwargs) -> Response:
        return super().list(request, *args, **kwargs)


# --- Réponse aux invitations (RG-20) -------------------------------------------------------


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=128)


class AcceptSerializer(serializers.Serializer):
    """Jeton d'invitation (``token``) ou lien de liaison d'adresse (``link``), l'un ou l'autre."""

    token = serializers.CharField(max_length=128, required=False)
    link = serializers.CharField(max_length=512, required=False)

    def validate(self, attrs):
        if bool(attrs.get("token")) == bool(attrs.get("link")):
            raise serializers.ValidationError("Fournir « token » ou « link ».")
        return attrs


class InvitationLookupSerializer(serializers.Serializer):
    edition_code = serializers.CharField()
    edition_title_fr = serializers.CharField()
    edition_title_en = serializers.CharField()
    role = serializers.ChoiceField(choices=InvitableRole.choices)
    oc_function = serializers.CharField()
    inviter_name = serializers.CharField()
    email_masked = serializers.CharField()
    status = serializers.ChoiceField(choices=InvitationStatus.choices)
    expires_at = serializers.DateTimeField()
    message = serializers.CharField()
    controls_address = serializers.BooleanField(
        help_text="Vrai si le compte connecté porte déjà l'adresse invitée, vérifiée."
    )


class AcceptedRoleSerializer(serializers.Serializer):
    edition_id = serializers.IntegerField()
    role = serializers.CharField()


class InvitationLookupView(APIView):
    """``POST /v1/invitations/lookup`` : public, CSRF imposé, limité (§5.7)."""

    permission_classes = (AllowAny, CsrfEnforced)
    throttle_scope = "invitation"

    @extend_schema(
        operation_id="invitation_lookup",
        request=TokenSerializer,
        responses={200: InvitationLookupSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        info = invitation_services.lookup(serializer.validated_data["token"], request.user)
        return Response(InvitationLookupSerializer(info).data)


class InvitationDeclineView(APIView):
    """``POST /v1/invitations/decline`` : refus sans compte (aucun droit donné)."""

    permission_classes = (AllowAny, CsrfEnforced)
    throttle_scope = "invitation"

    @extend_schema(
        operation_id="invitation_decline", request=TokenSerializer, responses={204: None}
    )
    def post(self, request: Request) -> Response:
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation_services.decline(
            serializer.validated_data["token"], actor=Actor.from_request(request)
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationAcceptView(APIView):
    """``POST /v1/invitations/accept`` : connecté ; ``{link}`` exige une réauthentification
    récente (plan v3), ``{token}`` non (aucune adresse ajoutée au compte)."""

    permission_classes = (IsAuthenticated,)
    throttle_scope = "invitation"

    @extend_schema(
        operation_id="invitation_accept",
        request=AcceptSerializer,
        responses={200: AcceptedRoleSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = Actor.from_request(request)
        link = serializer.validated_data.get("link")
        if link:
            if not has_recent_authentication(request):
                raise _reauthentication_required()
            user_role = invitation_services.accept_with_link(link, user=request.user, actor=actor)
        else:
            user_role = invitation_services.accept(
                serializer.validated_data["token"], user=request.user, actor=actor
            )
        return Response({"edition_id": user_role.edition_id, "role": user_role.role})


class InvitationLinkEmailView(APIView):
    """``POST /v1/invitations/link-email`` : lien de liaison envoyé à l'adresse invitée
    (RG-20, option (a) de D6) ; réauthentification récente, limite ``invitation_link``."""

    permission_classes = (IsAuthenticated, RecentAuthRequired)
    throttle_scope = "invitation_link"

    @extend_schema(
        operation_id="invitation_link_email", request=TokenSerializer, responses={204: None}
    )
    def post(self, request: Request) -> Response:
        serializer = TokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation_services.request_email_link(
            serializer.validated_data["token"],
            user=request.user,
            actor=Actor.from_request(request),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
