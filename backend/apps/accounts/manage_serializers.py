"""Sérialiseurs des membres, invitations et du journal d'une édition (plan L1 §5.4, §5.7, §7.4).

Minimisation (§5.1, 4ᵉ étage) : l'adresse e-mail des membres et des invités n'est
renvoyée qu'avec ``members.manage`` ; sinon, sérialiseur sans adresse (échec fermé).
"""

from __future__ import annotations

from rest_framework import serializers

from apps.accounts.models import (
    MESSAGE_MAX_LENGTH,
    InvitationStatus,
    RoleInvitation,
    RoleSource,
    UserRole,
    UserRoleStatus,
)
from apps.accounts.roles import InvitableRole, OcFunction, Role
from apps.accounts.serializers import Locale
from apps.accounts.services.invitations import (
    MAX_EMAILS_PER_REQUEST,
    SkippedReason,
    display_name,
)
from apps.core.actor import ActorKind
from apps.core.audit import mask_email
from apps.core.models import AuditLog


class MemberSerializer(serializers.ModelSerializer):
    """Membre d'une édition, sans adresse (``members.read`` seul)."""

    user_id = serializers.IntegerField(source="user.pk", read_only=True)
    name = serializers.SerializerMethodField()
    role = serializers.ChoiceField(choices=Role.choices, read_only=True)
    oc_function = serializers.ChoiceField(choices=OcFunction.choices, read_only=True)
    status = serializers.ChoiceField(choices=UserRoleStatus.choices, read_only=True)
    source = serializers.ChoiceField(choices=RoleSource.choices, read_only=True)

    class Meta:
        model = UserRole
        fields = (
            "id",
            "user_id",
            "name",
            "role",
            "oc_function",
            "status",
            "source",
            "granted_at",
            "revoked_at",
        )
        read_only_fields = fields

    def get_name(self, user_role: UserRole) -> str:
        return display_name(user_role.user)


class MemberWithEmailSerializer(MemberSerializer):
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta(MemberSerializer.Meta):
        fields = (*MemberSerializer.Meta.fields, "email")
        read_only_fields = fields


class RevokeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)


class InvitationSerializer(serializers.ModelSerializer):
    """Invitation, adresse masquée (``members.read`` seul)."""

    email = serializers.SerializerMethodField()
    role = serializers.ChoiceField(choices=InvitableRole.choices, read_only=True)
    oc_function = serializers.ChoiceField(choices=OcFunction.choices, read_only=True)
    status = serializers.ChoiceField(choices=InvitationStatus.choices, read_only=True)
    invited_by_name = serializers.SerializerMethodField()

    class Meta:
        model = RoleInvitation
        fields = (
            "id",
            "email",
            "role",
            "oc_function",
            "status",
            "locale",
            "invited_by_name",
            "expires_at",
            "send_count",
            "last_sent_at",
            "responded_at",
            "created_at",
        )
        read_only_fields = fields

    def get_email(self, invitation: RoleInvitation) -> str:
        return mask_email(invitation.email)

    def get_invited_by_name(self, invitation: RoleInvitation) -> str:
        return display_name(invitation.invited_by)


class InvitationWithEmailSerializer(InvitationSerializer):
    def get_email(self, invitation: RoleInvitation) -> str:
        return invitation.email


class InvitationCreateSerializer(serializers.Serializer):
    emails = serializers.ListField(
        child=serializers.CharField(max_length=254),
        min_length=1,
        max_length=MAX_EMAILS_PER_REQUEST,
    )
    role = serializers.ChoiceField(choices=InvitableRole.choices)
    oc_function = serializers.ChoiceField(
        choices=OcFunction.choices, required=False, allow_blank=True, default=""
    )
    locale = serializers.ChoiceField(choices=Locale.choices, required=False)
    message = serializers.CharField(
        max_length=MESSAGE_MAX_LENGTH, required=False, allow_blank=True, default=""
    )


class SkippedInvitationSerializer(serializers.Serializer):
    email = serializers.CharField(help_text="Adresse masquée.")
    reason = serializers.ChoiceField(choices=SkippedReason.choices)


class InvitationBatchSerializer(serializers.Serializer):
    created = InvitationWithEmailSerializer(many=True)
    skipped = SkippedInvitationSerializer(many=True)


class AuditEntrySerializer(serializers.ModelSerializer):
    """Entrée du journal d'une édition, **sans IP ni navigateur** (minimisation, §7.4)."""

    actor_kind = serializers.ChoiceField(choices=ActorKind.choices, read_only=True)
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "at",
            "action",
            "actor_kind",
            "actor_id",
            "actor_name",
            "object_type",
            "object_id",
            "before",
            "after",
            "reason",
        )
        read_only_fields = fields

    def get_actor_name(self, entry: AuditLog) -> str:
        if entry.actor_id:
            return display_name(entry.actor)
        return entry.actor_label
